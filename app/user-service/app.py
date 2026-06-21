from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({
        "service": "user-service",
        "status": "running"
    })

@app.route("/users")
def users():
    return jsonify([
        {
            "user_id": 1,
            "name": "Shiva"
        }
    ])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)