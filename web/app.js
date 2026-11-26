// Pairs this phone with Facelock on a computer, and approves unlocks with the phone's passkey.
// Nothing here is secret on its own: the computer checks every signature against the passkey it
// saved at pairing, and only for a challenge it made itself.

import {b64url, challengeFor, derivePairing, normalizeCode, randomBytes, seal, unb64url} from './crypto.js?v=4';

const DEFAULT_RELAY = 'https://ntfy.sh';
const COMPUTERS_KEY = 'facelock.computers';
const VAPID_KEY = 'facelock.vapid';

const $ = id => document.getElementById(id);

// --- Storage: what this phone knows about each paired computer, by relay topic. --- //

function loadComputers() {
    try {
        return JSON.parse(localStorage.getItem(COMPUTERS_KEY)) ?? {};
    } catch {
        return {};
    }
}

function saveComputers(computers) {
    localStorage.setItem(COMPUTERS_KEY, JSON.stringify(computers));
}

// One VAPID key for every computer this phone pairs with, since a page can only have one push
// subscription. Each computer gets the private half, so it can send to this phone.
async function vapidKey() {
    const stored = localStorage.getItem(VAPID_KEY);
    if (stored)
        return JSON.parse(stored);
    const pair = await crypto.subtle.generateKey({name: 'ECDSA', namedCurve: 'P-256'}, true, ['sign']);
    const {d, x, y} = await crypto.subtle.exportKey('jwk', pair.privateKey);
    const raw = b64url(await crypto.subtle.exportKey('raw', pair.publicKey));
    const key = {d, x, y, raw};
    localStorage.setItem(VAPID_KEY, JSON.stringify(key));
    return key;
}

// --- Small helpers --- //

function show(id) {
    for (const section of document.querySelectorAll('main > section'))
        section.hidden = section.id !== id;
}

function status(text, error = false) {
    $('status').textContent = text;
    $('status').classList.toggle('error', error);
}

function standalone() {
    return navigator.standalone === true || matchMedia('(display-mode: standalone)').matches;
}

function iOS() {
    return /iPhone|iPad|iPod/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function deviceName() {
    if (/iPhone/.test(navigator.userAgent))
        return 'iPhone';
    if (/iPad/.test(navigator.userAgent) || iOS())
        return 'iPad';
    if (/Android/.test(navigator.userAgent))
        return 'Android phone';
    return 'Browser';
}

async function post(relay, topic, body, keep) {
    const response = await fetch(`${relay.replace(/\/+$/, '')}/${topic}`, {
        method: 'POST',
        body,
        headers: keep ? {} : {Cache: 'no'},
    });
    if (!response.ok)
        throw new Error(`The relay answered ${response.status}`);
}

// --- Pairing --- //

async function registerWorker() {
    const registration = await navigator.serviceWorker.register('sw.js');
    await navigator.serviceWorker.ready;
    return registration;
}

async function allowNotifications() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window))
        throw new Error('This browser can\'t receive notifications from a web page.');
    const permission = await Notification.requestPermission();
    if (permission !== 'granted')
        throw new Error('Notifications are off. Allow them for Facelock in the phone\'s settings.');
    await registerWorker();
}

async function pushSubscription() {
    const registration = await registerWorker();
    const vapid = await vapidKey();
    const existing = await registration.pushManager.getSubscription();
    if (existing) {
        const current = existing.options?.applicationServerKey;
        if (!current || b64url(current) === vapid.raw)
            return existing;
        await existing.unsubscribe(); // made with a key this page no longer has
    }
    return registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: unb64url(vapid.raw)});
}

async function pair(code, name, relay) {
    if (normalizeCode(code).length !== 12)
        throw new Error('The code has 12 letters and digits.');
    // Created first, while the tap still counts as one: Safari asks for it.
    const credential = await navigator.credentials.create({
        publicKey: {
            rp: {id: location.hostname, name: 'Facelock'},
            user: {id: randomBytes(16), name: `Facelock: ${name}`, displayName: `Facelock: ${name}`},
            challenge: randomBytes(32),
            pubKeyCredParams: [{type: 'public-key', alg: -7}],
            // This phone's own passkeys, such as Google Password Manager or iCloud Keychain,
            // not a security key or another device.
            // Passkey apps on Android only make passkeys kept whole on the phone, so ask for that.
            authenticatorSelection: {authenticatorAttachment: 'platform', userVerification: 'required',
                residentKey: 'required', requireResidentKey: true},
            attestation: 'none',
            timeout: 120000,
        },
    });
    if (credential.response.getPublicKeyAlgorithm?.() !== -7)
        throw new Error('The passkey doesn\'t use a key type Facelock can check.');
    const publicKey = credential.response.getPublicKey();

    status('Pairing…');
    const subscription = (await pushSubscription()).toJSON();
    const vapid = await vapidKey();
    const relayTopic = `facelock-${[...randomBytes(16)].map(b => b.toString(16).padStart(2, '0')).join('')}`;
    const relayKey = randomBytes(32);
    const reply = {
        credential: b64url(credential.rawId),
        public_key: b64url(publicKey),
        subscription: {endpoint: subscription.endpoint, keys: subscription.keys},
        vapid: {d: vapid.d, x: vapid.x, y: vapid.y},
        topic: relayTopic,
        key: b64url(relayKey),
        device: deviceName(),
    };
    const pairing = await derivePairing(code);
    await post(relay, pairing.topic, await seal(pairing.key, pairing.topic, reply), true);

    const computers = loadComputers();
    computers[relayTopic] = {
        name, relay, key: b64url(relayKey), credential: b64url(credential.rawId), pairedAt: Date.now(),
    };
    saveComputers(computers);
}

function startPairing(code = '', name = '', relay = DEFAULT_RELAY) {
    if (iOS() && !standalone()) {
        $('install-code').textContent = code;
        show('install');
        return;
    }
    show('pair');
    $('code').value = code;
    $('relay').value = relay;
    $('pair-title').textContent = name ? `Pair with ${name}` : 'Pair with your computer';
    const granted = 'Notification' in window && Notification.permission === 'granted';
    $('notify-button').disabled = granted;
    $('notify-button').textContent = granted ? 'Notifications allowed' : 'Allow notifications';
    $('passkey-button').disabled = !granted;

    $('notify-button').onclick = async () => {
        try {
            await allowNotifications();
            $('notify-button').disabled = true;
            $('notify-button').textContent = 'Notifications allowed';
            $('passkey-button').disabled = false;
            status('');
        } catch (error) {
            status(error.message, true);
        }
    };
    $('passkey-button').onclick = async () => {
        $('passkey-button').disabled = true;
        try {
            await pair($('code').value, name || 'computer', $('relay').value || DEFAULT_RELAY);
            history.replaceState(null, '', location.pathname);
            showHome();
            status('Paired. A test notification is on its way.');
        } catch (error) {
            $('passkey-button').disabled = false;
            console.error(error);
            status(error.name === 'NotAllowedError'
                ? 'The passkey wasn\'t created. The phone needs somewhere to keep passkeys: on Android, ' +
                  'Google Password Manager or another passkey app, turned on in Settings, Passwords and accounts.'
                : `${error.name}: ${error.message}`, true);
        }
    };
    $('code-form').onsubmit = event => event.preventDefault();
}

// --- Approving --- //

async function answer(request, computer, pick) {
    const nonce = unb64url(request.nonce);
    const assertion = await navigator.credentials.get({
        publicKey: {
            challenge: await challengeFor(nonce, pick),
            rpId: location.hostname,
            allowCredentials: [{type: 'public-key', id: unb64url(computer.credential)}],
            userVerification: 'required',
            timeout: 60000,
        },
    });
    const response = assertion.response;
    return {
        nonce: request.nonce,
        pick,
        credential: b64url(assertion.rawId),
        client_data: b64url(response.clientDataJSON),
        authenticator_data: b64url(response.authenticatorData),
        signature: b64url(response.signature),
    };
}

async function send(request, computer, value) {
    const key = unb64url(computer.key);
    await post(computer.relay, request.topic, await seal(key, request.topic, value), false);
}

function showApproval(request) {
    const computer = loadComputers()[request.topic];
    if (!computer) {
        showHome();
        status('That request came from a computer this phone isn\'t paired with.', true);
        return;
    }
    if (request.expires * 1000 < Date.now()) {
        showHome();
        status('That request has expired. Try unlocking again.', true);
        return;
    }
    show('approve');
    status('');
    $('approve-title').textContent = `Unlock ${request.name || computer.name}?`;
    const numbers = $('numbers');
    numbers.replaceChildren();

    const buttons = [];
    const approve = async pick => {
        buttons.forEach(button => (button.disabled = true));
        try {
            const value = await answer(request, computer, pick);
            status('Sending…');
            await send(request, computer, value);
            status('Approved. Your computer is unlocking.');
            numbers.hidden = true;
            $('approve-button').hidden = true;
            $('deny-button').hidden = true;
        } catch (error) {
            buttons.forEach(button => (button.disabled = false));
            status(error.name === 'NotAllowedError' ? 'Not approved.' : error.message, true);
        }
    };

    if (Array.isArray(request.numbers)) {
        $('approve-hint').textContent = 'Tap the number shown on your computer\'s lock screen.';
        numbers.hidden = false;
        $('approve-button').hidden = true;
        for (const number of request.numbers) {
            const button = document.createElement('button');
            button.textContent = String(number);
            button.onclick = () => approve(number);
            numbers.append(button);
            buttons.push(button);
        }
    } else {
        $('approve-hint').textContent = 'Only approve if you are at the computer.';
        numbers.hidden = true;
        $('approve-button').hidden = false;
        $('approve-button').onclick = () => approve(null);
        buttons.push($('approve-button'));
    }
    $('deny-button').hidden = false;
    $('deny-button').onclick = async () => {
        try {
            await send(request, computer, {nonce: request.nonce, deny: true});
            status('Declined. The computer stays locked.');
        } catch (error) {
            status(error.message, true);
        }
        showHome();
    };
    buttons.push($('deny-button'));
}

// --- The paired computers --- //

function showHome() {
    show('home');
    const computers = loadComputers();
    const list = $('computers');
    list.replaceChildren();
    for (const [topic, computer] of Object.entries(computers)) {
        const item = document.createElement('li');
        const label = document.createElement('span');
        label.textContent = computer.name;
        const forget = document.createElement('button');
        forget.textContent = 'Forget';
        forget.onclick = () => {
            const remaining = loadComputers();
            delete remaining[topic];
            saveComputers(remaining);
            showHome();
            status(`Forgotten. Also remove the passkey "Facelock: ${computer.name}" from the phone's passwords.`);
        };
        item.append(label, forget);
        list.append(item);
    }
    $('no-computers').hidden = Object.keys(computers).length > 0;
    $('pair-another').onclick = () => startPairing();
}

// --- Diagnostics: which page version this is, and whether the phone can keep a passkey. --- //

const PAGE_VERSION = 4;

async function diagnose() {
    let platform = 'unknown';
    try {
        platform = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable() ? 'yes' : 'no';
    } catch {
        platform = 'no passkey support';
    }
    $('diagnostics').textContent = `Page version ${PAGE_VERSION} · Passkeys on this phone: ${platform}`;
    if (platform !== 'yes') {
        status('This browser can\'t keep a passkey on this phone. On Android, turn on Google Password ' +
            'Manager or another passkey app in Settings, Passwords and accounts, and set a screen lock.', true);
    }
}

// --- Routing --- //

function decodeRequest(text) {
    try {
        return JSON.parse(new TextDecoder().decode(unb64url(text)));
    } catch {
        return null;
    }
}

function route() {
    const params = new URLSearchParams(location.hash.slice(1));
    if (params.has('r')) {
        const request = decodeRequest(params.get('r'));
        history.replaceState(null, '', location.pathname);
        if (request) {
            showApproval(request);
            return;
        }
    }
    if (params.has('pair')) {
        startPairing(params.get('pair'), params.get('name') ?? '', params.get('relay') ?? DEFAULT_RELAY);
        return;
    }
    if (Object.keys(loadComputers()).length === 0)
        startPairing();
    else
        showHome();
}

// The notification hands an open page the request directly, rather than reloading it.
navigator.serviceWorker?.addEventListener('message', event => {
    if (event.data?.type === 'unlock')
        showApproval(event.data.request);
});
navigator.serviceWorker?.register('sw.js').catch(() => {});
addEventListener('hashchange', route);
route();
diagnose();
