from flask import Flask, render_template, request, redirect, url_for, flash, session
from config import Config
from models import db, bcrypt, User, Patient, Procedure, Appointment
from routes import api
from flask_migrate import Migrate
from datetime import datetime
from functools import wraps
import re

def format_cpf(value):
    if not value:
        return ""
    digits = re.sub(r'\D', '', value)
    if len(digits) == 11:
        return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
    return value

def format_telefone(value):
    if not value:
        return ""
    digits = re.sub(r'\D', '', value)
    if len(digits) == 11:
        return f'({digits[:2]}) {digits[2]} {digits[3:7]}-{digits[7:]}'
    if len(digits) == 10: 
        return f'({digits[:2]}) {digits[2:6]}-{digits[6:]}'
    return value

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.jinja_env.filters['cpf'] = format_cpf
    app.jinja_env.filters['telefone'] = format_telefone

    db.init_app(app)
    bcrypt.init_app(app)
    Migrate(app, db)

    app.register_blueprint(api, url_prefix='/api')

    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Por favor, faça login para acessar esta página.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Por favor, faça login para acessar esta página.', 'danger')
                return redirect(url_for('login'))
            user = User.query.get(session['user_id'])
            if user and user.tipo != 'admin':
                flash('Você não tem permissão para acessar esta página.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function

    @app.route("/login", methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email')
            senha = request.form.get('senha')
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(senha):
                session['user_id'] = user.id
                session['user_nome'] = user.nome
                session['user_tipo'] = user.tipo 
                flash(f'Login bem-sucedido! Bem-vindo, {user.nome}.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Email ou senha inválidos. Tente novamente.', 'danger')
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.clear()
        flash('Você saiu do sistema.', 'success')
        return redirect(url_for('login'))
    
    @app.route("/")
    @login_required
    def index():
        page = request.args.get('page', 1, type=int)
        pacientes_paginados = Patient.query.order_by(Patient.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("index.html", pagination=pacientes_paginados, endpoint='index')

    @app.route("/users")
    @admin_required
    def user_list():
        page = request.args.get('page', 1, type=int)
        usuarios_paginados = User.query.order_by(User.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("users.html", pagination=usuarios_paginados, endpoint='user_list')
    
    @app.route('/users/new', methods=['GET', 'POST'])
    @admin_required
    def create_user():
        if request.method == 'POST':
            new_user = User(
                nome=request.form['nome'],
                email=request.form['email'],
                tipo=request.form['tipo']
            )
            new_user.set_password(request.form['senha'])
            db.session.add(new_user)
            db.session.commit()
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('user_list'))
        return render_template('user_form.html')

    @app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
    @admin_required
    def edit_user(user_id):
        user = User.query.get_or_404(user_id)
        if request.method == 'POST':
            user.nome = request.form['nome']
            user.email = request.form['email']
            user.tipo = request.form['tipo']
            senha = request.form.get('senha')
            if senha:
                user.set_password(senha)
            db.session.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('user_list'))
        return render_template('user_form.html', user=user)

    @app.route('/users/delete/<int:user_id>', methods=['POST'])
    @admin_required
    def delete_user(user_id):
        if user_id == session.get('user_id'):
            flash('Você não pode remover a si mesmo.', 'danger')
            return redirect(url_for('user_list'))
        user = User.query.get_or_404(user_id)
        db.session.delete(user)
        db.session.commit()
        flash('Usuário removido com sucesso.', 'success')
        return redirect(url_for('user_list'))

    # --- ROTAS DE PROCEDIMENTOS (CRUD COMPLETO E PROTEGIDO) ---
    @app.route("/procedures")
    @login_required 
    def procedure_list():
        page = request.args.get('page', 1, type=int)
        procedimentos_paginados = Procedure.query.order_by(Procedure.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("procedures.html", pagination=procedimentos_paginados, endpoint='procedure_list')

    @app.route('/procedures/new', methods=['GET', 'POST'])
    @admin_required
    def create_procedure():
        if request.method == 'POST':
            new_procedure = Procedure(
                nome=request.form['nome'],
                descricao=request.form.get('descricao'),
                valor_plano_saude=request.form['valor_plano_saude'],
                valor_particular=request.form['valor_particular']
            )
            db.session.add(new_procedure)
            db.session.commit()
            flash('Procedimento criado com sucesso!', 'success')
            return redirect(url_for('procedure_list'))
        return render_template('procedure_form.html')
    
    @app.route('/procedures/edit/<int:procedure_id>', methods=['GET', 'POST'])
    @admin_required
    def edit_procedure(procedure_id):
        procedure = Procedure.query.get_or_404(procedure_id)
        if request.method == 'POST':
            procedure.nome = request.form['nome']
            procedure.descricao = request.form.get('descricao')
            procedure.valor_plano_saude = request.form['valor_plano_saude']
            procedure.valor_particular = request.form['valor_particular']
            db.session.commit()
            flash('Procedimento atualizado com sucesso!', 'success')
            return redirect(url_for('procedure_list'))
        return render_template('procedure_form.html', procedure=procedure)

    @app.route('/procedures/delete/<int:procedure_id>', methods=['POST'])
    @admin_required
    def delete_procedure(procedure_id):
        procedure = Procedure.query.get_or_404(procedure_id)
        db.session.delete(procedure)
        db.session.commit()
        flash('Procedimento removido com sucesso.', 'success')
        return redirect(url_for('procedure_list'))
    
    # --- ROTAS DE ATENDIMENTOS ---
    @app.route("/appointments")
    @login_required
    def appointment_list():
        page = request.args.get('page', 1, type=int)
        atendimentos_paginados = db.session.query(Appointment).join(Patient).order_by(Appointment.data_atendimento.desc()).paginate(page=page, per_page=10, error_out=False)
        return render_template("appointments.html", pagination=atendimentos_paginados, endpoint='appointment_list')

    @app.route('/appointments/new', methods=['GET', 'POST'])
    @login_required
    def create_appointment_form():
        if request.method == 'POST':
            paciente_id = request.form.get('paciente_id')
            procedure_ids = request.form.getlist('procedure_ids') 
            data_str = request.form.get('data_atendimento')
            tipo = request.form.get('tipo')
            numero_carteira = request.form.get('numero_carteira_plano')

            if not all([paciente_id, procedure_ids, data_str, tipo]):
                flash('Erro: Todos os campos são obrigatórios.', 'danger')
                return redirect(url_for('create_appointment_form'))

            valor_total_calculado = 0
            procedimentos_selecionados = Procedure.query.filter(Procedure.id.in_(procedure_ids)).all()
            
            for procedimento in procedimentos_selecionados:
                if tipo == 'plano':
                    valor_total_calculado += procedimento.valor_plano_saude
                else: 
                    valor_total_calculado += procedimento.valor_particular

            novo_atendimento = Appointment(
                paciente_id=paciente_id,
                data_atendimento=datetime.strptime(data_str, '%Y-%m-%dT%H:%M'),
                tipo=tipo,
                numero_carteira_plano=numero_carteira if tipo == 'plano' else None,
                usuario_id=session['user_id'],
                valor_total=valor_total_calculado
            )
            novo_atendimento.procedures.extend(procedimentos_selecionados)

            db.session.add(novo_atendimento)
            db.session.commit()
            
            flash('Atendimento criado com sucesso!', 'success')
            return redirect(url_for('appointment_list'))

        pacientes = Patient.query.order_by(Patient.nome).all()
        procedimentos = Procedure.query.order_by(Procedure.nome).all()
        return render_template('appointment_form.html', pacientes=pacientes, procedimentos=procedimentos)
    
    # --- ROTAS DE PACIENTES ---
    @app.route('/patients/new', methods=['GET', 'POST'])
    @login_required
    def create_patient():
        if request.method == 'POST':
            data_nascimento = datetime.strptime(request.form['data_nascimento'], '%Y-%m-%d').date()
            novo_paciente = Patient(
                nome=request.form['nome'], cpf=request.form['cpf'], email=request.form['email'],
                telefone=request.form['telefone'], data_nascimento=data_nascimento,
                cep=request.form['cep'], rua=request.form['rua'], numero=request.form['numero'],
                bairro=request.form['bairro'], cidade=request.form['cidade'], estado=request.form['estado'],
                responsavel_nome=request.form.get('responsavel_nome'),
                responsavel_cpf=request.form.get('responsavel_cpf')
            )
            db.session.add(novo_paciente)
            db.session.commit()
            flash('Paciente cadastrado com sucesso!', 'success')
            return redirect(url_for('index'))
        return render_template('patient_form.html')

    @app.route('/patients/edit/<int:patient_id>', methods=['GET', 'POST'])
    @login_required
    def edit_patient(patient_id):
        patient = Patient.query.get_or_404(patient_id)
        if request.method == 'POST':
            patient.nome = request.form['nome']
            patient.cpf = request.form['cpf']
            patient.email = request.form['email']
            patient.telefone = request.form['telefone']
            patient.data_nascimento = datetime.strptime(request.form['data_nascimento'], '%Y-%m-%d').date()
            patient.cep = request.form['cep']
            patient.rua = request.form['rua']
            patient.numero = request.form['numero']
            patient.bairro = request.form['bairro']
            patient.cidade = request.form['cidade']
            patient.estado = request.form['estado']
            patient.responsavel_nome = request.form.get('responsavel_nome')
            patient.responsavel_cpf = request.form.get('responsavel_cpf')
            db.session.commit()
            flash('Dados do paciente atualizados com sucesso!', 'success')
            return redirect(url_for('index'))
        return render_template('patient_form.html', patient=patient)

    @app.route('/patients/delete/<int:patient_id>', methods=['POST'])
    @login_required
    def delete_patient(patient_id):
        patient = Patient.query.get_or_404(patient_id)
        if Appointment.query.filter_by(paciente_id=patient_id).first():
            flash('Não é possível remover um paciente com atendimentos vinculados.', 'danger')
            return redirect(url_for('index'))
        
        db.session.delete(patient)
        db.session.commit()
        flash('Paciente removido com sucesso.', 'success')
        return redirect(url_for('index'))

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=8080)