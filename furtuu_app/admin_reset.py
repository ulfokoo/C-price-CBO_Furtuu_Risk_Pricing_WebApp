from flask import Flask
from database import DATABASE_URL
from app import db
from app.models import User

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

NEW_USERNAME = "admin"
NEW_PASSWORD = "admin123"   # change this to whatever you want, then run once

with app.app_context():
    user = User.query.filter_by(username=NEW_USERNAME).first()
    if user:
        user.set_password(NEW_PASSWORD)
        user.role = "admin"
        db.session.commit()
        print(f"Password for '{NEW_USERNAME}' reset.")
    else:
        user = User(username=NEW_USERNAME, role="admin")
        user.set_password(NEW_PASSWORD)
        db.session.add(user)
        db.session.commit()
        print(f"Admin user '{NEW_USERNAME}' created.")