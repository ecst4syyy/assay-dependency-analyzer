from flask import current_app
from flask_wtf import FlaskForm
from wtforms import EmailField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length, Optional, Regexp, ValidationError

from app.services.passwords import MAX_PASSWORD_LENGTH, password_problems

# Deliberately simple; see DECISIONS D-03 (no email-validator dependency).
EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$"


class RegisterForm(FlaskForm):
    email = EmailField(
        "Email",
        validators=[
            DataRequired(),
            Length(max=255),
            Regexp(EMAIL_PATTERN, message="Enter a valid email address."),
        ],
    )
    display_name = StringField("Display name (optional)", validators=[Optional(), Length(max=100)])
    password = PasswordField("Password", validators=[DataRequired()])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )
    submit = SubmitField("Create account")

    def validate_password(self, field):
        problems = password_problems(
            field.data or "", self.email.data, current_app.config["PASSWORD_MIN_LENGTH"]
        )
        if problems:
            raise ValidationError(" ".join(problems))


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Length(max=255)])
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(max=MAX_PASSWORD_LENGTH)]
    )
    submit = SubmitField("Log in")
