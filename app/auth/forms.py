from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Regexp, Optional
class LoginForm(FlaskForm):
    email=StringField('Email', validators=[DataRequired(), Email()]); password=PasswordField('Password', validators=[DataRequired()]); remember=BooleanField('Remember me'); submit=SubmitField('Login')
class RegisterForm(FlaskForm):
    full_name=StringField('Full name', validators=[DataRequired(), Length(min=2, max=120)])
    email=StringField('Email ID', validators=[DataRequired(), Email()])
    password=PasswordField('Password', validators=[DataRequired(), Length(min=8), Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).+$', message='Password must include uppercase, lowercase, number and special character.')])
    confirm_password=PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')])
    mobile=StringField('Mobile number', validators=[Optional(), Regexp(r'^(?:\+91[6-9]\d{9}|[6-9]\d{9})$', message='Enter a valid 10-digit Indian mobile number.')])
    work_status=SelectField('Work status', choices=[('fresher','Fresher'),('experienced','Experienced')], validators=[Optional()])
    role=SelectField('Account type', choices=[('candidate','Job Seeker'),('recruiter','Recruiter')])
    submit=SubmitField('Register now')
class ForgotPasswordForm(FlaskForm):
    email=StringField('Email', validators=[DataRequired(), Email()]); submit=SubmitField('Send reset link')
class ResetPasswordForm(FlaskForm):
    password=PasswordField('New password', validators=[DataRequired(), Length(min=8), Regexp(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).+$', message='Password must include uppercase, lowercase, number and special character.')]); confirm_password=PasswordField('Confirm password', validators=[DataRequired(), EqualTo('password')]); submit=SubmitField('Reset password')
