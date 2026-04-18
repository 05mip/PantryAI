import logging

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, redirect, g
from flask_cors import CORS

from config import FLASK_SECRET_KEY, DEFAULT_USER_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pantryai")

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

CORS(app, supports_credentials=True)

from routes.pantry import pantry_bp
from routes.recipes import recipes_bp
from routes.grocery import grocery_bp
from routes.meals import meals_bp
from routes.chat import chat_bp

app.register_blueprint(pantry_bp)
app.register_blueprint(recipes_bp)
app.register_blueprint(grocery_bp)
app.register_blueprint(meals_bp)
app.register_blueprint(chat_bp)


@app.before_request
def set_default_user():
    g.user_id = DEFAULT_USER_ID


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/pantry")
def pantry_page():
    return render_template("pantry.html")


@app.route("/recipes")
def recipes_page():
    return render_template("recipes.html")


@app.route("/grocery")
def grocery_page():
    return render_template("grocery.html")


@app.route("/meals")
def meals_page():
    return render_template("meals.html")


@app.errorhandler(404)
def not_found(e):
    return {"success": False, "error": "Not found"}, 404


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {e}")
    return {"success": False, "error": "Internal server error"}, 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
