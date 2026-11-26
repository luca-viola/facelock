// The page's half of what extension/daemon/phone.py and relay.py do. Both must agree exactly.

const encoder = new TextEncoder();

export function b64url(bytes) {
    const data = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : bytes;
    let text = '';
    for (const byte of data)
        text += String.fromCharCode(byte);
    return btoa(text).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function unb64url(text) {
    const padded = text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (text.length % 4)) % 4);
    return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
}

export function randomBytes(length) {
    return crypto.getRandomValues(new Uint8Array(length));
}

function concat(...parts) {
    const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
    let offset = 0;
    for (const part of parts) {
        out.set(part, offset);
        offset += part.length;
    }
    return out;
}

// The code as the computer showed it, without dashes or spaces, in capitals.
export function normalizeCode(code) {
    return code.toUpperCase().replace(/[^A-Z0-9]/g, '');
}

// The pairing topic and key, from the code. Same as derive_pairing() in phone.py.
export async function derivePairing(code) {
    const material = await crypto.subtle.importKey(
        'raw', encoder.encode(normalizeCode(code)), 'HKDF', false, ['deriveBits']);
    const derive = async (info, bits) => new Uint8Array(await crypto.subtle.deriveBits(
        {name: 'HKDF', hash: 'SHA-256', salt: encoder.encode('facelock pairing'), info: encoder.encode(info)},
        material, bits));
    const topicBytes = await derive('topic', 128);
    const topic = `facelock-${[...topicBytes].map(b => b.toString(16).padStart(2, '0')).join('')}`;
    return {topic, key: await derive('key', 256)};
}

// AES-256-GCM over the JSON, bound to the topic. Same as seal() in relay.py.
export async function seal(keyBytes, topic, value) {
    const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['encrypt']);
    const iv = randomBytes(12);
    const sealed = await crypto.subtle.encrypt(
        {name: 'AES-GCM', iv, additionalData: encoder.encode(topic)},
        key, encoder.encode(JSON.stringify(value)));
    return b64url(concat(iv, new Uint8Array(sealed)));
}

export async function unseal(keyBytes, topic, text) {
    const data = unb64url(text.trim());
    const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['decrypt']);
    const plain = await crypto.subtle.decrypt(
        {name: 'AES-GCM', iv: data.slice(0, 12), additionalData: encoder.encode(topic)},
        key, data.slice(12));
    return JSON.parse(new TextDecoder().decode(plain));
}

// What the passkey signs. Same as challenge_for() in phone.py.
export async function challengeFor(nonce, pick) {
    const pickBytes = encoder.encode(pick === null || pick === undefined ? '' : String(pick));
    return new Uint8Array(await crypto.subtle.digest('SHA-256', concat(nonce, pickBytes)));
}

// What the page's own device key signs, where the phone can't make a passkey. Same as
// DEVICE_KEY_CONTEXT and verify_device_signature() in phone.py.
const DEVICE_KEY_CONTEXT = encoder.encode('facelock device-key approval\0');

export async function deviceSign(privateKey, challenge) {
    return new Uint8Array(await crypto.subtle.sign(
        {name: 'ECDSA', hash: 'SHA-256'}, privateKey, concat(DEVICE_KEY_CONTEXT, challenge)));
}

// A signing key the page can use but nobody can copy out, not even the page.
export async function newDeviceKey() {
    const pair = await crypto.subtle.generateKey({name: 'ECDSA', namedCurve: 'P-256'}, false, ['sign']);
    return {privateKey: pair.privateKey, spki: new Uint8Array(await crypto.subtle.exportKey('spki', pair.publicKey))};
}
