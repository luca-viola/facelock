#!flask/bin/python
import os
import numpy as np
import cv2
import face_recognition
from flask import Flask, request, redirect, url_for,flash
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = '/tmp'
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'gif'])

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

faceName = "Tome Duarte"

imageFolder = "/home/lviola/Pictures/faces"
faces_files = [f for f in os.listdir(imageFolder)]

known_face_encodings = [
]
known_face_names = [
]

for face_file in faces_files:
  imagePath = imageFolder + "/" + face_file
  targetFaceName = face_file.replace("_"," ",3).split(".")[0]
  target_face = face_recognition.load_image_file(imagePath)
  target_face_encoding = face_recognition.face_encodings(target_face)[0]
  known_face_encodings.append(target_face_encoding)
  known_face_names.append(targetFaceName)


@app.route('/')
def index():
    return "Hello, World!"


@app.route('/greet/<string:name>', methods=['GET'])
def verify(name):
  return "Hello, "+name+"!"


def allowed_file(filename):
  return '.' in filename and \
         filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
  name = "Unknown"

  if request.method == 'POST':
    # check if the post request has the file part
    if 'file' not in request.files:
      flash('No file part')
      return redirect(request.url)
    file = request.files['file']
    # if user does not select file, browser also
    # submit a empty part without filename
    if file.filename == '':
      flash('No selected file')
      return redirect(request.url)
    if file and allowed_file(file.filename):
      filename = secure_filename(file.filename)
      img_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
      file.save(img_path)

      try:
        frame = cv2.imread(img_path, 1)
        small_frame = None
      except cv2.error as e:
        app.logger.error('textError parsing uploaded image', e)

      small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
      rgb_small_frame = small_frame[:, :, ::-1]
      face_locations = face_recognition.face_locations(rgb_small_frame)
      face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

      face_names = []
      for face_encoding in face_encodings:
        matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
        name = "Unknown"

        if True in matches:
          first_match_index = matches.index(True)
          name = known_face_names[first_match_index]
          app.logger.info('%s recognized successfully', name)
        face_names.append(name)

      return redirect(url_for('upload_file', filename=filename, name=name))
  return """
    <!doctype html>
    <html>
      <head>
        <title>Upload new File</title>
      </head>
      <body>  
        <h1>Upload new File</h1>
        <form method=post enctype=multipart/form-data>
          <p><input type=file name=file>
             <input type=submit value=Upload>
        </form>
        <div>Face belongs to: <input type="text" id="name" /></div>
        <script type="application/javascript">
          function querySt(ji) {
          
              hu = window.location.search.substring(1);
              gy = hu.split("&");
          
              for (i=0;i<gy.length;i++) {
                  ft = gy[i].split("=");
                  if (ft[0] == ji) {
                      return ft[1];
                  }
              }
          }
          var name = querySt("name");        
          document.getElementById('name').value = name;
        </script>
      </body>
    </html>
    """


if __name__ == '__main__':
    app.run(debug=True)
