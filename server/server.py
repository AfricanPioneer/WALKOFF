import os
import ssl
import json

from flask import Flask, jsonify, request, render_template
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.security import Security, SQLAlchemyUserDatastore, UserMixin, RoleMixin, login_required
from flask_security import auth_token_required, current_user, roles_required
from flask_security.utils import encrypt_password, verify_and_update_password
from core import forms
from jinja2 import Environment, FileSystemLoader
from core.ffk import Flag
from core.workflow import Workflow

from core import config, appBlueprint, interface


app = Flask(__name__, static_folder=os.path.abspath('server/static'))

app.jinja_loader = FileSystemLoader(['server/templates'])

app.register_blueprint(appBlueprint.appPage, url_prefix='/apps/<app>')

app.config.update(
    # CHANGE SECRET KEY AND SECURITY PASSWORD SALT!!!
    SECRET_KEY="SHORTSTOPKEYTEST",
    SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.abspath(config.dbPath),
    SECURITY_PASSWORD_HASH='pbkdf2_sha512',
    SECURITY_TRACKABLE=False,
    SECURITY_PASSWORD_SALT='something_super_secret_change_in_production',
    SECURITY_POST_LOGIN_VIEW='/',
    WTF_CSRF_ENABLED=False
)

# Template Loader
env = Environment(loader=FileSystemLoader("apps"))

app.config["SECURITY_LOGIN_USER_TEMPLATE"] = "login_user.html"

# Database Connection Object
db = SQLAlchemy(app)


# Base Class for Tables
class Base(db.Model):
    __abstract__ = True
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    modified_at = db.Column(db.DateTime, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())


# Define Models
roles_users = db.Table('roles_users',
                       db.Column('user_id', db.Integer(), db.ForeignKey('auth_user.id')),
                       db.Column('role_id', db.Integer(), db.ForeignKey('auth_role.id')))


class Role(Base, RoleMixin):
    __tablename__ = 'auth_role'
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

    def __init__(self, name, description):
        self.name = name
        self.description = description

    def setDescription(self, description):
        self.description = description

    def toString(self):
        return {"name": self.name, "description": self.description}

    def __repr__(self):
        return '<Role %r>' % self.name


class User(Base, UserMixin):
    __tablename__ = 'auth_user'
    email = db.Column(db.String(255), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean())
    confirmed_at = db.Column(db.DateTime())
    roles = db.relationship('Role', secondary=roles_users, backref=db.backref('users', lazy='dynamic'))

    last_login_at = db.Column(db.DateTime())
    current_login_at = db.Column(db.DateTime())
    last_login_ip = db.Column(db.String(45))
    current_login_ip = db.Column(db.String(45))
    login_count = db.Column(db.Integer)

    def display(self):
        result = {}
        result["username"] = self.email
        roles = [role.toString() for role in self.roles]
        result["roles"] = roles
        result["active"] = self.active

        return results

    def setRoles(self, roles):
        for role in roles:
            if role.data != "" and not self.has_role(role.data):
                q = user_datastore.find_role(role.data)
                if q is not None:
                    user_datastore.add_role_to_user(self, q)
                    print("ADDED ROLE")
                else:
                    print("ROLE DOES NOT EXIST")
            else:
                print("HAS ROLE")

    def __repr__(self):
        return '<User %r>' % self.email


# Setup Flask Security
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)


# Creates Test Data
@app.before_first_request
def create_user():
    # db.drop_all()
    db.create_all()
    if not User.query.first():
        # Add Credentials to Splunk app
        # db.session.add(Device(name="deviceOne", app="splunk", username="admin", password="hello", ip="192.168.0.1", port="5000"))

        adminRole = user_datastore.create_role(name="admin", description="administrator")
        # userRole = user_datastore.create_role(name="user", description="user")

        u = user_datastore.create_user(email='admin', password=encrypt_password('admin'))
        # u2 = user_datastore.create_user(email='user', password=encrypt_password('user'))

        user_datastore.add_role_to_user(u, adminRole)

        db.session.commit()

class Triggers(Base):
    __tablename__ = "triggers"
    name = db.Column(db.String(255), nullable=False)
    play = db.Column(db.String(255), nullable=False)
    condition = db.Column(db.String(255, convert_unicode=False), nullable=False)

    def __init__(self, name, play, condition):
        self.name = name
        self.play = play
        self.condition = condition

    def edit_trigger(self, form=None):
        if form:
            if form.name.data:
                self.name = form.name.data

            if form.play.data:
                self.play = form.play.data

            if form.conditional.data:
                self.condition = str(form.conditional.data)

        return True

    def as_json(self):
        return {'name': self.name,
                'conditions': self.condition,
                'play': self.play}

    @staticmethod
    def execute(data_in):
        triggers = Triggers.query.all()
        listener_output = {}
        for trigger in triggers:
            conditionals = json.loads(trigger.condition)
            if all(Triggers.__execute_trigger(conditional, data_in) for conditional in conditionals):
                workflow_to_be_executed = Workflow.get_workflow(trigger.play)
                if workflow_to_be_executed:
                    trigger_results = workflow_to_be_executed.execute()
                else:
                    return json.dumps({"status": "trigger error: play could not be found"})
                listener_output[trigger.name] = json.loads(str(trigger_results[0]))
        return listener_output

    @staticmethod
    def __execute_trigger(conditional, data_in):
        conditional = json.loads(conditional)
        return Flag(**conditional)(data_in)

    def __repr__(self):
        return json.dumps(self.as_json())

    def __str__(self):
        out = {'name': self.name,
               'conditions': json.loads(self.condition),
               'play': self.play}
        return json.dumps(out)

""""
    URLS
"""


@app.route("/")
@login_required
def default():
    if current_user.is_authenticated:
        args = {"apps": config.getApps(), "authKey": current_user.get_auth_token(), "currentUser": current_user.email}
        return render_template("container.html", **args)
    else:
        return {"status": "Could Not Log In."}


@app.route("/workflow/", methods=['GET'])
def workflow():
    return ""


@app.route("/configuration/<string:key>", methods=['POST'])
@auth_token_required
@roles_required("admin")
def configValues(key):
    if current_user.is_authenticated and key:
        if hasattr(config, key):
            return json.dumps({str(key): str(getattr(config, key))})


# Returns System-Level Interface Pages
@app.route('/interface/<string:name>/display', methods=["POST"])
@auth_token_required
@roles_required("admin")
def systemPages(name):
    if current_user.is_authenticated and name:
        args, form = getattr(interface, name)()
        return render_template("pages/" + name + "/index.html", form=form, **args)
    else:
        return {"status": "Could Not Log In."}


# Controls execution triggers
@app.route('/execution/listener', methods=["POST"])
@auth_token_required
@roles_required("admin")
def listener():
    form = forms.incomingDataForm(request.form)
    listener_output = Triggers.execute(form.data.data) if form.validate() else {}
    return json.dumps(listener_output)


@app.route('/execution/listener/triggers/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def triggerManagement(action):
    if action == "add":
        form = forms.addNewTriggerForm(request.form)
        if form.validate():
            query = Triggers.query.filter_by(name=form.name.data).first()
            if query is None:
                db.session.add(
                    Triggers(name=form.name.data, condition=json.dumps(form.conditional.data), play=form.play.data))
                db.session.commit()

                return json.dumps({"status": "trigger successfully added"})
        return json.dumps({"status": "trigger could not be added"})


@app.route('/execution/listener/triggers/<string:name>/<string:action>', methods=["POST"])
@auth_token_required
@roles_required("admin")
def triggerFunctions(action, name):
    if action == "edit":
        form = forms.editTriggerForm(request.form)
        trigger = Triggers.query.filter_by(name=name).first()
        if form.validate() and trigger is not None:
            # Ensures new name is unique
            if form.name.data:
                if len(Triggers.query.filter_by(name=form.name.data).all()) > 0:
                    return json.dumps({"status": "device could not be edited"})

            result = trigger.editTrigger(form)

            if result:
                db.session.commit()
                return json.dumps({"status": "device successfully edited"})

        return json.dumps({"status": "device could not be edited"})

    elif action == "remove":
        query = Triggers.query.filter_by(name=name).first()
        if query:
            Triggers.query.filter_by(name=name).delete()
            db.session.commit()
            return json.dumps({"status": "removed trigger"})
        return json.dumps({"status": "could not remove trigger"})

    elif action == "display":
        query = Triggers.query.filter_by(name=name).first()
        if query:
            return str(query)
        return json.dumps({"status": "could not display trigger"})


# Start Flask
def start(config_type=None):
    global db, env

    if config.https.lower() == "true":
        # Sets up HTTPS
        if config.TLS_version == "1.2":
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        elif config.TLS_version == "1.1":
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_1)
        else:
            context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)

        # Provide user with informative error message
        displayIfFileNotFound(config.certificatePath)
        displayIfFileNotFound(config.privateKeyPath)

        context.load_cert_chain(config.certificatePath, config.privateKeyPath)
        app.run(debug=config.debug, ssl_context=context, host=config.host, port=int(config.port), threaded=True)
    else:
        app.run(debug=config.debug, host=config.host, port=int(config.port), threaded=True)


def displayIfFileNotFound(filepath):
    if not os.path.isfile(filepath):
        print("File not found: " + filepath)
