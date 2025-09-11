from flask import Flask, render_template, request
from config import Config
from models import db, bcrypt, User, Patient, Procedure
from routes import api
from flask_migrate import Migrate

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    bcrypt.init_app(app)
    Migrate(app, db)

    app.register_blueprint(api, url_prefix='/api')

    @app.route("/")
    def index():
        page = request.args.get('page', 1, type=int)
        pacientes_paginados = Patient.query.order_by(Patient.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("index.html", pagination=pacientes_paginados, endpoint='index')
  
    @app.route("/users")
    def user_list():
        page = request.args.get('page', 1, type=int)
        usuarios_paginados = User.query.order_by(User.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("users.html", pagination=usuarios_paginados, endpoint='user_list')

    @app.route("/procedures")
    def procedure_list():
        page = request.args.get('page', 1, type=int)
        procedimentos_paginados = Procedure.query.order_by(Procedure.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("procedures.html", pagination=procedimentos_paginados, endpoint='procedure_list')

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=8080)