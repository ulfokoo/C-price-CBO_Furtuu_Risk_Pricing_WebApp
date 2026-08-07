from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from app import db
from app.models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboards.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f"Welcome back, {user.username}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboards.home"))
        flash("Invalid username or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboards.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.", "danger")
        else:
            user = User(username=username, role="user")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Account created. You can now log in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/signup.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/users", methods=["GET", "POST"])
@login_required
def manage_users():
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboards.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "user")
        if not username or not password:
            flash("Username and password are required.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("That username already exists.", "danger")
        else:
            u = User(username=username, role=role)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash(f"User '{username}' created as {role}.", "success")
        return redirect(url_for("auth.manage_users"))

    users = User.query.order_by(User.username).all()
    return render_template("auth/users.html", users=users)


@auth_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash("Admin access required.", "danger")
        return redirect(url_for("dashboards.home"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account while logged in.", "warning")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("User deleted.", "info")
    return redirect(url_for("auth.manage_users"))
