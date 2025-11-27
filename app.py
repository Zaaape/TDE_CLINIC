from flask import Flask, render_template, request, redirect, url_for, flash, session
from config import Config
from models import db, bcrypt, User, Patient, Procedure, Appointment
from routes import api
from flask_migrate import Migrate
from datetime import datetime
from functools import wraps
import re

# Estas funções formatam dados "feios" do banco para ficarem bonitos no HTML.
# Exemplo: Transforma "12345678900" em "123.456.789-00"

def format_cpf(value):
    if not value:
        return ""
    digits = re.sub(r'\D', '', value) # Remove tudo que não for dígito
    if len(digits) == 11:
        return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
    return value

def format_telefone(value):
    if not value:
        return ""
    digits = re.sub(r'\D', '', value)
    if len(digits) == 11: # Celular
        return f'({digits[:2]}) {digits[2]} {digits[3:7]}-{digits[7:]}'
    if len(digits) == 10: # Fixo
        return f'({digits[:2]}) {digits[2:6]}-{digits[6:]}'
    return value

# O Flask usa esse padrão para criar o app. Facilita testes e configurações.

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config) # Carrega variáveis de ambiente (.env)

    # Registra os filtros criados acima para usar no HTML como {{ valor | cpf }}
    app.jinja_env.filters['cpf'] = format_cpf
    app.jinja_env.filters['telefone'] = format_telefone

    # Inicializa plugins/extensões
    db.init_app(app)       # Banco de dados
    bcrypt.init_app(app)   # Criptografia de senhas
    Migrate(app, db)       # Ferramenta de migração (alterar tabelas sem perder dados)

    # Registra o Blueprint da API (conecta o routes.py a este app)
    app.register_blueprint(api, url_prefix='/api')
 
    # 1. Login Required: Verifica se o usuário tem uma sessão ativa. Se não tiver, joga ele para a tela de login.
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session: 
                flash('Por favor, faça login para acessar esta página.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

    # 2. Admin Required: Verifica se, além de logado, o tipo do usuário é 'admin'.
    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Por favor, faça login para acessar esta página.', 'danger')
                return redirect(url_for('login'))
            
            # Busca o usuário no banco para conferir o tipo atualizado
            user = User.query.get(session['user_id'])
            if user and user.tipo != 'admin':
                flash('Você não tem permissão para acessar esta página.', 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function

    # --- ROTA DE LOGIN/LOGOUT ---

    @app.route("/login", methods=['GET', 'POST'])
    def login():
        # Se for POST, o usuário clicou em "Entrar" no formulário
        if request.method == 'POST':
            email = request.form.get('email')
            senha = request.form.get('senha')
            
            user = User.query.filter_by(email=email).first()
            
            # Verifica hash da senha
            if user and user.check_password(senha):
                # Cria a sessão do usuário (login bem-sucedido)
                session['user_id'] = user.id
                session['user_nome'] = user.nome
                session['user_tipo'] = user.tipo 
                flash(f'Login bem-sucedido! Bem-vindo, {user.nome}.', 'success')
                return redirect(url_for('index'))
            else:
                flash('Email ou senha inválidos. Tente novamente.', 'danger')
        
        # Se for GET, apenas mostra o formulário HTML
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        session.clear() # Apaga os dados da sessão (desloga)
        flash('Você saiu do sistema.', 'success')
        return redirect(url_for('login'))
    
    # --- ROTA PRINCIPAL (DASHBOARD/PACIENTES) ---
    
    @app.route("/")
    @login_required
    def index():
        # Paginação: Mostra 10 pacientes por página para não travar o sistema
        page = request.args.get('page', 1, type=int)
        pacientes_paginados = Patient.query.order_by(Patient.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("index.html", pagination=pacientes_paginados, endpoint='index')

    # --- GESTÃO DE USUÁRIOS (APENAS ADMIN) ---

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
            # Cria objeto User com dados do formulário
            new_user = User(
                nome=request.form['nome'],
                email=request.form['email'],
                tipo=request.form['tipo']
            )
            # Define a senha (o método set_password faz o hash automaticamente)
            new_user.set_password(request.form['senha'])
            db.session.add(new_user)
            db.session.commit()
            flash('Usuário criado com sucesso!', 'success')
            return redirect(url_for('user_list'))
        return render_template('user_form.html')

    @app.route('/users/edit/<int:user_id>', methods=['GET', 'POST'])
    @admin_required
    def edit_user(user_id):
        user = User.query.get_or_404(user_id) # Se não achar o ID, retorna erro 404
        if request.method == 'POST':
            user.nome = request.form['nome']
            user.email = request.form['email']
            user.tipo = request.form['tipo']
            
            # Só altera a senha se o campo foi preenchido
            senha = request.form.get('senha')
            if senha:
                user.set_password(senha)
                
            db.session.commit() # O SQLAlchemy detecta mudanças e faz o UPDATE
            flash('Usuário atualizado com sucesso!', 'success')
            return redirect(url_for('user_list'))
        # Reutiliza o mesmo formulário de criação, mas passando o objeto 'user' para preencher os campos
        return render_template('user_form.html', user=user)

    @app.route('/users/delete/<int:user_id>', methods=['POST'])
    @admin_required
    def delete_user(user_id):
        # Proteção para não deixar o admin apagar a si mesmo
        if user_id == session.get('user_id'):
            flash('Você não pode remover a si mesmo.', 'danger')
            return redirect(url_for('user_list'))
        
        user = User.query.get_or_404(user_id)
        
        # Buscamos TODOS os atendimentos vinculados a este usuário
        atendimentos_do_usuario = Appointment.query.filter_by(usuario_id=user_id).all()
        
        if atendimentos_do_usuario:
            # Montamos uma mensagem listando as datas e os pacientes desses atendimentos
            detalhes = []
            for a in atendimentos_do_usuario:
                data_fmt = a.data_atendimento.strftime('%d/%m/%Y')
                # Como temos o relacionamento .patient, podemos pegar o nome do paciente
                detalhes.append(f"{data_fmt} (Pac: {a.patient.nome})")
            
            # Junta tudo numa string separada por vírgula
            msg_erro = f"Não é possível excluir {user.nome}. Ele(a) é responsável pelos atendimentos: {', '.join(detalhes)}. Exclua esses atendimentos antes de remover o usuário."
            
            flash(msg_erro, 'danger')
            return redirect(url_for('user_list'))

        db.session.delete(user)
        db.session.commit()
        flash('Usuário removido com sucesso.', 'success')
        return redirect(url_for('user_list'))

    # --- PROCEDIMENTOS (CRUD COMPLETO) ---
    
    @app.route("/procedures")
    @login_required # Qualquer usuário logado pode VER a lista
    def procedure_list():
        page = request.args.get('page', 1, type=int)
        procedimentos_paginados = Procedure.query.order_by(Procedure.nome).paginate(page=page, per_page=10, error_out=False)
        return render_template("procedures.html", pagination=procedimentos_paginados, endpoint='procedure_list')

    @app.route('/procedures/new', methods=['GET', 'POST'])
    @admin_required # Apenas ADMIN pode CRIAR (controlar preços)
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
    
    # --- ATENDIMENTOS ---
    
    @app.route("/appointments")
    @login_required
    def appointment_list():
        page = request.args.get('page', 1, type=int)
    
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = db.session.query(Appointment).join(Patient)
        
        if start_date and end_date:
            try:
                s_date = datetime.strptime(start_date, '%Y-%m-%d')
                e_date = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                query = query.filter(Appointment.data_atendimento.between(s_date, e_date))
            except ValueError:
                flash('Datas inválidas para o filtro.', 'warning')
        
        # Ordenação e Paginação
        atendimentos_paginados = query.order_by(Appointment.data_atendimento.desc()).paginate(page=page, per_page=10, error_out=False)
        
        return render_template("appointments.html", pagination=atendimentos_paginados, endpoint='appointment_list')

    @app.route('/appointments/new', methods=['GET', 'POST'])
    @login_required
    def create_appointment_form():
        if request.method == 'POST':
            # Captura dados complexos do formulário
            paciente_id = request.form.get('paciente_id')
            procedure_ids = request.form.getlist('procedure_ids') 
            data_str = request.form.get('data_atendimento')
            tipo = request.form.get('tipo') # 'plano' ou 'particular'
            numero_carteira = request.form.get('numero_carteira_plano')

            # Validação no Backend
            if not all([paciente_id, procedure_ids, data_str, tipo]):
                flash('Erro: Todos os campos são obrigatórios.', 'danger')
                return redirect(url_for('create_appointment_form'))

            # Cálculo do valor total
            valor_total_calculado = 0
            procedimentos_selecionados = Procedure.query.filter(Procedure.id.in_(procedure_ids)).all()
            
            for procedimento in procedimentos_selecionados:
                if tipo == 'plano':
                    valor_total_calculado += procedimento.valor_plano_saude
                else: 
                    valor_total_calculado += procedimento.valor_particular

            # Criação do objeto
            novo_atendimento = Appointment(
                paciente_id=paciente_id,
                data_atendimento=datetime.strptime(data_str, '%Y-%m-%dT%H:%M'), # Converte string HTML para DateTime Python
                tipo=tipo,
                numero_carteira_plano=numero_carteira if tipo == 'plano' else None,
                usuario_id=session['user_id'], # Registra quem criou
                valor_total=valor_total_calculado
            )
            
            novo_atendimento.procedures.extend(procedimentos_selecionados)

            db.session.add(novo_atendimento)
            db.session.commit()
            
            flash('Atendimento criado com sucesso!', 'success')
            return redirect(url_for('appointment_list'))

        # Para o GET, precisamos enviar as listas de pacientes e procedimentos para preencher os <select> e <checkbox>
        pacientes = Patient.query.order_by(Patient.nome).all()
        procedimentos = Procedure.query.order_by(Procedure.nome).all()
        return render_template('appointment_form.html', pacientes=pacientes, procedimentos=procedimentos)
    
    # --- PACIENTES ---
    
    @app.route('/patients/new', methods=['GET', 'POST'])
    @login_required
    def create_patient():
        if request.method == 'POST':
            # 1. Verifica duplicidade ANTES de tentar salvar
            if Patient.query.filter_by(cpf=request.form['cpf']).first():
                flash('Erro: Já existe um paciente com este CPF.', 'danger')
                return render_template('patient_form.html', patient=None) 
            
            if Patient.query.filter_by(email=request.form['email']).first():
                flash('Erro: Já existe um paciente com este E-mail.', 'danger')
                return render_template('patient_form.html', patient=None)

            # 2. Validação de Idade e Responsável
            data_nasc = datetime.strptime(request.form['data_nascimento'], '%Y-%m-%d').date()
            idade = (datetime.now().date() - data_nasc).days / 365.25
            
            resp_nome = request.form.get('responsavel_nome')
            resp_cpf = request.form.get('responsavel_cpf')
            
            if idade < 18 and (not resp_nome or not resp_cpf):
                flash('Erro: Para menores de 18 anos, os dados do responsável são obrigatórios.', 'danger')
                return render_template('patient_form.html', patient=None)

            # Se passou, cria o paciente
            novo_paciente = Patient(
                nome=request.form['nome'], cpf=request.form['cpf'], email=request.form['email'],
                telefone=request.form['telefone'], data_nascimento=data_nasc,
                cep=request.form['cep'], rua=request.form['rua'], numero=request.form['numero'],
                bairro=request.form['bairro'], cidade=request.form['cidade'], estado=request.form['estado'],
                responsavel_nome=resp_nome,
                responsavel_cpf=resp_cpf
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
            # Atualização manual campo a campo
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
        
        # Integridade Referencial: Não apagar paciente se ele tiver consultas
        if Appointment.query.filter_by(paciente_id=patient_id).first():
            flash('Não é possível remover um paciente com atendimentos vinculados.', 'danger')
            return redirect(url_for('index'))
        
        db.session.delete(patient)
        db.session.commit()
        flash('Paciente removido com sucesso.', 'success')
        return redirect(url_for('index'))

    # VISUALIZAR DETALHES DO ATENDIMENTO ---
    @app.route('/appointments/<int:appointment_id>')
    @login_required
    def view_appointment(appointment_id):
        appointment = Appointment.query.get_or_404(appointment_id)
        return render_template('appointment_details.html', appointment=appointment)

    # DELETAR ATENDIMENTO ---
    @app.route('/appointments/delete/<int:appointment_id>', methods=['POST'])
    @login_required
    def delete_appointment(appointment_id):
        appointment = Appointment.query.get_or_404(appointment_id)
        # Permissão: Apenas Admin ou quem criou pode deletar
        if appointment.usuario_id != session['user_id'] and session['user_tipo'] != 'admin':
            flash('Você não tem permissão para excluir este atendimento.', 'danger')
            return redirect(url_for('appointment_list'))
            
        db.session.delete(appointment)
        db.session.commit()
        flash('Atendimento removido com sucesso.', 'success')
        return redirect(url_for('appointment_list'))

    return app

# Bloco para rodar o app localmente em modo de desenvolvimento
if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=8080)