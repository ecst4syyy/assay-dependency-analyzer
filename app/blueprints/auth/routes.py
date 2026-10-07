"""Registration, login and logout."""

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.audit import record_event
from app.blueprints.auth import bp
from app.blueprints.auth.forms import LoginForm, RegisterForm
from app.extensions import limiter
from app.services.accounts import authenticate, register_user

LOGIN_FAILED = "Invalid email or password, or the account is temporarily locked."


def _safe_next(target):
    """Only allow same-site relative redirects (prevents open redirects)."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("scan.new")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("scan.new"))
    form = RegisterForm()
    if form.validate_on_submit():
        register_user(form.email.data, form.password.data, form.display_name.data)
        # Same message whether or not the email was already registered, so the
        # form cannot be used to discover who has an account.
        flash(
            "If that email address was not already registered, your account has been "
            "created. Please log in.",
            "success",
        )
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("scan.new"))
    form = LoginForm()
    if form.validate_on_submit():
        result = authenticate(form.email.data, form.password.data)
        if result.ok:
            # Throw away everything in the pre-login session so nothing an
            # attacker planted survives (session fixation, SPEC §11).
            next_url = _safe_next(request.args.get("next"))
            session.clear()
            session.permanent = True
            login_user(result.user)
            return redirect(next_url)
        flash(LOGIN_FAILED, "error")
    return render_template("auth/login.html", form=form)


@bp.post("/logout")
@login_required
def logout():
    user_id = current_user.id
    logout_user()
    session.clear()
    record_event("LOGOUT", user_id=user_id)
    flash("You have been logged out.", "success")
    return redirect(url_for("main.index"))
