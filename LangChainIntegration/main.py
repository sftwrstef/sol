from app import app # Import Flask app directly

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
