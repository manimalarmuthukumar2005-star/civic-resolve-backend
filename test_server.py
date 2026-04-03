"""
Run this to test if backend is working:
  python test_server.py
Then open: http://localhost:5000/test
"""
from flask import Flask, jsonify
app = Flask(__name__)

@app.after_request
def cors(r):
    r.headers['Access-Control-Allow-Origin']  = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return r

@app.route('/test')
def test():
    return jsonify({'status': 'ok', 'message': 'Backend is working!'})

if __name__ == '__main__':
    print("✅ Test server running at http://localhost:5000/test")
    app.run(port=5000, debug=False)
