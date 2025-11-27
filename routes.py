from flask import Blueprint, request, jsonify, current_app
from models import db, User, Patient, Appointment, Procedure, appointment_procedures
import jwt
import datetime
from functools import wraps
import os

# Cria um 'Blueprint' para organizar as rotas da API pra permitir que essas rotas sejam registradas no app principal (app.py) com um prefixo (ex: /api).

api = Blueprint('api', __name__)

# --- FUNÇÕES DE AUTENTICAÇÃO ---

def generate_token(user):
    """
    Gera um token JWT (JSON Web Token) para um usuário autenticado.
    O token contém informações (payload) e é assinado com uma chave secreta.
    """
    try:
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1),
            'iat': datetime.datetime.utcnow(),
            'sub': str(user.id),
            # 'tipo': Incluímos o tipo de usuário no token para facilitar verificações no front-end
            'tipo': user.tipo
        }
        return jwt.encode(
            payload,
            current_app.config.get('SECRET_KEY'),
            algorithm='HS256'
        )
    except Exception as e:
        return e

def token_required(f):
   
    #Decorator (decorador) para proteger rotas. Verifica se a requisição possui um token JWT válido no cabeçalho.

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Verifica se o cabeçalho 'Authorization' está presente na requisição
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]

        # Se não houver token, retorna erro 401 (Não Autorizado)
        if not token:
            return jsonify({'message': 'Token é obrigatório!'}), 401

        try:
            # Tenta decodificar o token usando a chave secreta do app
            data = jwt.decode(token, current_app.config.get('SECRET_KEY'), algorithms=['HS256'])
            # Se der certo, busca o usuário no banco pelo ID que estava no token ('sub')
            current_user = User.query.get(data['sub'])
        except:
            # Se o token for inválido ou expirado
            return jsonify({'message': 'Token inválido!'}), 401
        
        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    #Decorator para restringir acesso apenas a administradores. Deve ser usado DEPOIS de @token_required.
    @wraps(f)
    def decorated(current_user, *args, **kwargs):
        # Verifica o campo 'tipo' do usuário carregado do banco
        if current_user.tipo != 'admin':
            return jsonify({'message': 'Acesso negado. Requer privilégios de administrador.'}), 403
        return f(current_user, *args, **kwargs)
    return decorated


# --- ROTA DE LOGIN ---

@api.route('/login', methods=['POST'])
def login():
    
    # Rota pública para autenticação. Recebe JSON com email e senha e retorna um token JWT se as credenciais forem válidas.
    
    auth = request.get_json()
    # Validação básica de entrada
    if not auth or not auth.get('email') or not auth.get('senha'):
        return jsonify({'message': 'Email e senha são obrigatórios!'}), 400

    # Busca usuário no banco pelo email
    user = User.query.filter_by(email=auth['email']).first()
    
    # Verifica se usuário existe E se a senha bate com o hash (usando método do model)
    if not user or not user.check_password(auth['senha']):
        return jsonify({'message': 'Credenciais inválidas!'}), 401

    # Gera e retorna o token
    token = generate_token(user)
    return jsonify({'token': token})


# --- ROTAS DE USUÁRIOS (CRUD) ---

@api.route('/users', methods=['POST'])
@token_required # Exige estar logado
@admin_required # Exige ser admin
def create_user(current_user):
    # Cria um novo usuário (apenas Admin pode fazer isso)."""
    data = request.get_json()
    # Valida campos obrigatórios
    if not data or not data.get('email') or not data.get('senha') or not data.get('nome'):
        return jsonify({'message': 'Dados incompletos!'}), 400

    # Verifica duplicidade de email
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'message': 'Usuário com este e-mail já existe.'}), 409

    # Cria instância do usuário. Senha é tratada separadamente pelo método set_password
    new_user = User(
        email=data['email'],
        nome=data['nome'],
        tipo=data.get('tipo', 'default') # Se não enviar tipo, assume 'default'
    )
    new_user.set_password(data['senha']) # Hash da senha
    
    db.session.add(new_user) 
    db.session.commit()      
    
    return jsonify(new_user.to_json()), 201

@api.route('/users/<int:user_id>', methods=['PUT'])
@token_required
def update_user(current_user, user_id):
    # Atualiza dados do usuário. O próprio usuário só pode alterar a si mesmo."""
    # Garante que usuário comum não altere dados de outro usuário
    if current_user.id != user_id:
        return jsonify({'message': 'Acesso não autorizado para atualizar este usuário.'}), 403

    user_to_update = User.query.get_or_404(user_id)
    data = request.get_json()

    # Atualiza campos se eles foram enviados no JSON
    user_to_update.nome = data.get('nome', user_to_update.nome)
    
    # Lógica especial para email (verificar se o novo email já não existe)
    new_email = data.get('email')
    if new_email and new_email != user_to_update.email:
        if User.query.filter_by(email=new_email).first():
            return jsonify({'message': 'Este e-mail já está em uso.'}), 409
        user_to_update.email = new_email
        
    db.session.commit()
    return jsonify(user_to_update.to_json()), 200

@api.route('/users/<int:user_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_user(current_user, user_id):
    # Remove um usuário (apenas Admin).
    # Proteção: Admin não pode se deletar
    if current_user.id == user_id:
        return jsonify({'message': 'Um administrador não pode remover a si mesmo.'}), 403
    
    # Proteção: Integridade referencial (não apagar usuário com atendimentos feitos)
    atendimento_existente = Appointment.query.filter_by(usuario_id=user_id).first()
    if atendimento_existente:
        return jsonify({'message': 'Não é possível remover um usuário com atendimentos vinculados.'}), 409

    user_to_delete = User.query.get_or_404(user_id)
    db.session.delete(user_to_delete)
    db.session.commit()
    return jsonify({'message': f'Usuário {user_to_delete.nome} removido com sucesso.'}), 200


# --- ROTAS DE PACIENTES ---

@api.route('/patients', methods=['POST'])
@token_required
def create_patient(current_user):
    # Cadastra novo paciente com validação de idade/responsável.
    data = request.get_json()
    
    # Lista de campos obrigatórios
    required_fields = ["cpf", "nome", "email", "telefone", "data_nascimento", "estado", "cidade", "bairro", "cep", "rua", "numero"]
    if not all(field in data for field in required_fields):
        return jsonify({"message": "Campos obrigatórios do paciente faltando."}), 400
        
    # Verifica unicidade de CPF e Email
    if Patient.query.filter_by(cpf=data['cpf']).first():
        return jsonify({"message": "CPF já cadastrado."}), 409
    if Patient.query.filter_by(email=data['email']).first():
        return jsonify({"message": "Email já cadastrado."}), 409
        
    # Conversão de data string -> objeto date
    try:
        data_nascimento = datetime.datetime.strptime(data['data_nascimento'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"message": "Formato de data de nascimento inválido. Use AAAA-MM-DD."}), 400
        
    # REGRA DE NEGÓCIO: Validação de Menor de Idade
    age = (datetime.date.today() - data_nascimento).days / 365.25
    if age < 18:
        # Se for menor, exige dados do responsável
        required_guardian_fields = ["responsavel_cpf", "responsavel_nome", "responsavel_data_nascimento", "responsavel_email", "responsavel_telefone"]
        if not all(field in data for field in required_guardian_fields):
            return jsonify({"message": "Campos obrigatórios do responsável faltando para paciente menor de idade."}), 400
        
        # Valida se o responsável também não é menor de idade (opcional, mas boa prática)
        try:
            responsavel_data_nascimento = datetime.datetime.strptime(data['responsavel_data_nascimento'], '%Y-%m-%d').date()
            guardian_age = (datetime.date.today() - responsavel_data_nascimento).days / 365.25
            if guardian_age < 18:
                return jsonify({"message": "O responsável não pode ser menor de idade."}), 400
        except (ValueError, KeyError):
            return jsonify({"message": "Formato de data de nascimento do responsável inválido. Use AAAA-MM-DD."}), 400

    # Cria o objeto paciente
    novo_paciente = Patient(
        cpf=data['cpf'], nome=data['nome'], email=data['email'], telefone=data['telefone'], data_nascimento=data_nascimento,
        estado=data['estado'], cidade=data['cidade'], bairro=data['bairro'], cep=data['cep'], rua=data['rua'], numero=data['numero'],
        # Campos opcionais (usados apenas se for menor de idade)
        responsavel_cpf=data.get('responsavel_cpf'), responsavel_nome=data.get('responsavel_nome'),
        responsavel_data_nascimento=data.get('responsavel_data_nascimento'), responsavel_email=data.get('responsavel_email'),
        responsavel_telefone=data.get('responsavel_telefone')
    )
    db.session.add(novo_paciente)
    db.session.commit()
    return jsonify(novo_paciente.to_json()), 201

@api.route('/patients', methods=['GET'])
@token_required
def get_patients(current_user):
    # Lista pacientes com paginação.
    # Pega parâmetros da URL (ex: ?page=2&per_page=10)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 5, type=int)
    
    # Faz a query paginada no banco
    pagination = Patient.query.paginate(page=page, per_page=per_page, error_out=False)
    pacientes_da_pagina = pagination.items
    
    # Retorna estrutura JSON com metadados da paginação
    return jsonify({
        'pacientes': [paciente.to_json() for paciente in pacientes_da_pagina],
        'total_pacientes': pagination.total,
        'total_paginas': pagination.pages,
        'pagina_atual': pagination.page,
        'proxima_pagina': pagination.next_num,
        'pagina_anterior': pagination.prev_num
    })

@api.route('/patients/<int:patient_id>', methods=['GET'])
@token_required
def get_patient(current_user, patient_id):
    """Busca um único paciente pelo ID."""
    paciente = Patient.query.get_or_404(patient_id)
    return jsonify(paciente.to_json())

@api.route('/patients/<int:patient_id>', methods=['PUT'])
@token_required
def update_patient(current_user, patient_id):
    # Atualiza dados do paciente.
    paciente_a_atualizar = Patient.query.get_or_404(patient_id)
    data = request.get_json()
    
    # Validação: Não permitir remover responsável se o paciente ainda for menor
    if 'responsavel_cpf' in data and data.get('responsavel_cpf') is None and paciente_a_atualizar.responsavel_cpf:
        age = (datetime.date.today() - paciente_a_atualizar.data_nascimento).days / 365.25
        if age < 18:
            return jsonify({'message': 'Não é possível remover o responsável de um paciente menor de idade.'}), 403 

    # Validação de unicidade ao alterar CPF ou Email
    if 'cpf' in data and data['cpf'] != paciente_a_atualizar.cpf:
        if Patient.query.filter_by(cpf=data['cpf']).first():
            return jsonify({"message": "CPF já cadastrado em outro paciente."}), 409
    if 'email' in data and data['email'] != paciente_a_atualizar.email:
        if Patient.query.filter_by(email=data['email']).first():
            return jsonify({"message": "Email já cadastrado em outro paciente."}), 409

    # Atualiza os campos individualmente
    paciente_a_atualizar.nome = data.get('nome', paciente_a_atualizar.nome)
    paciente_a_atualizar.cpf = data.get('cpf', paciente_a_atualizar.cpf)
    paciente_a_atualizar.email = data.get('email', paciente_a_atualizar.email)
    paciente_a_atualizar.telefone = data.get('telefone', paciente_a_atualizar.telefone)
    
    if 'data_nascimento' in data:
        try:
            paciente_a_atualizar.data_nascimento = datetime.datetime.strptime(data['data_nascimento'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"message": "Formato de data de nascimento inválido. Use AAAA-MM-DD."}), 400
            
    # Atualiza endereço
    paciente_a_atualizar.estado = data.get('estado', paciente_a_atualizar.estado)
    paciente_a_atualizar.cidade = data.get('cidade', paciente_a_atualizar.cidade)
    paciente_a_atualizar.bairro = data.get('bairro', paciente_a_atualizar.bairro)
    paciente_a_atualizar.cep = data.get('cep', paciente_a_atualizar.cep)
    paciente_a_atualizar.rua = data.get('rua', paciente_a_atualizar.rua)
    paciente_a_atualizar.numero = data.get('numero', paciente_a_atualizar.numero)

    # Atualiza dados do responsável
    paciente_a_atualizar.responsavel_cpf = data.get('responsavel_cpf', paciente_a_atualizar.responsavel_cpf)
    paciente_a_atualizar.responsavel_nome = data.get('responsavel_nome', paciente_a_atualizar.responsavel_nome)
    paciente_a_atualizar.responsavel_data_nascimento = data.get('responsavel_data_nascimento', paciente_a_atualizar.responsavel_data_nascimento)
    paciente_a_atualizar.responsavel_email = data.get('responsavel_email', paciente_a_atualizar.responsavel_email)
    paciente_a_atualizar.responsavel_telefone = data.get('responsavel_telefone', paciente_a_atualizar.responsavel_telefone)

    db.session.commit()
    return jsonify(paciente_a_atualizar.to_json()), 200

@api.route('/patients/<int:patient_id>', methods=['DELETE'])
@token_required
def delete_patient(current_user, patient_id):
    # Remove paciente, verificando integridade referencial. Se o paciente já teve consultas, não pode deletar (histórico médico)
    atendimento_existente = Appointment.query.filter_by(paciente_id=patient_id).first()
    if atendimento_existente:
        return jsonify({'message': 'Não é possível remover um paciente com atendimentos vinculados.'}), 409
    
    paciente = Patient.query.get_or_404(patient_id)
    db.session.delete(paciente)
    db.session.commit()
    return jsonify({'message': f'Paciente {paciente.nome} removido com sucesso.'}), 200


# --- ROTAS DE PROCEDIMENTOS ---

@api.route('/procedures', methods=['POST'])
@token_required
@admin_required # Apenas admin cria procedimentos (para evitar alteração de preços por usuários comuns)
def create_procedure(current_user):
    data = request.get_json()
    required_fields = ["nome", "valor_plano_saude", "valor_particular"]
    if not all(field in data for field in required_fields):
        return jsonify({"message": "Campos obrigatórios faltando (nome, valor_plano_saude, valor_particular)."}), 400
    
    if Procedure.query.filter_by(nome=data['nome']).first():
        return jsonify({"message": "Já existe um procedimento com este nome."}), 409
        
    novo_procedimento = Procedure(
        nome=data['nome'],
        descricao=data.get('descricao'),
        valor_plano_saude=data['valor_plano_saude'],
        valor_particular=data['valor_particular']
    )
    db.session.add(novo_procedimento)
    db.session.commit()
    return jsonify(novo_procedimento.to_json()), 201

@api.route('/procedures', methods=['GET'])
@token_required
def get_procedures(current_user):
    """Lista procedimentos com paginação."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 5, type=int)
    pagination = Procedure.query.paginate(page=page, per_page=per_page, error_out=False)
    procedures_da_pagina = pagination.items
    return jsonify({
        'procedimentos': [procedure.to_json() for procedure in procedures_da_pagina],
        'total_procedimentos': pagination.total,
        'total_paginas': pagination.pages,
        'pagina_atual': pagination.page
    })

@api.route('/procedures/<int:procedure_id>', methods=['GET'])
@token_required
def get_procedure(current_user, procedure_id):
    procedimento = Procedure.query.get_or_404(procedure_id)
    return jsonify(procedimento.to_json())

@api.route('/procedures/<int:procedure_id>', methods=['PUT'])
@token_required
@admin_required
def update_procedure(current_user, procedure_id):
    procedimento = Procedure.query.get_or_404(procedure_id)
    data = request.get_json()
    
    if 'nome' in data and data['nome'] != procedimento.nome:
        if Procedure.query.filter_by(nome=data['nome']).first():
            return jsonify({"message": "Já existe um procedimento com este nome."}), 409
            
    procedimento.nome = data.get('nome', procedimento.nome)
    procedimento.descricao = data.get('descricao', procedimento.descricao)
    procedimento.valor_plano_saude = data.get('valor_plano_saude', procedimento.valor_plano_saude)
    procedimento.valor_particular = data.get('valor_particular', procedimento.valor_particular)
    
    db.session.commit()
    return jsonify(procedimento.to_json()), 200

@api.route('/procedures/<int:procedure_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_procedure(current_user, procedure_id):
    # Não remove procedimento se ele já foi usado em algum atendimento 
    atendimento_existente = db.session.query(appointment_procedures).filter_by(procedure_id=procedure_id).first()
    if atendimento_existente:
        return jsonify({'message': 'Não é possível remover um procedimento que já foi utilizado em um atendimento.'}), 409
        
    procedimento = Procedure.query.get_or_404(procedure_id)
    db.session.delete(procedimento)
    db.session.commit()
    return jsonify({'message': f'Procedimento {procedimento.nome} removido com sucesso.'}), 200


# --- ROTAS DE ATENDIMENTOS (AGENDAMENTOS) ---

@api.route('/appointments', methods=['POST'])
@token_required
def create_appointment(current_user):
    """Cria um agendamento, calculando o valor total com base nos procedimentos."""
    data = request.get_json()
    required_fields = ['data_atendimento', 'paciente_id', 'tipo', 'procedure_ids']
    
    # Validação inicial
    if not all(field in data for field in required_fields):
        return jsonify({"message": "Campos obrigatórios faltando."}), 400
    if not isinstance(data['procedure_ids'], list) or len(data['procedure_ids']) == 0:
        return jsonify({"message": "O atendimento precisa ter pelo menos um procedimento."}), 400
    if data['tipo'] == 'plano' and not data.get('numero_carteira_plano'):
        return jsonify({"message": "Número da carteira do plano é obrigatório para atendimentos do tipo 'plano'."}), 400
        
    paciente = Patient.query.get(data['paciente_id'])
    if not paciente:
        return jsonify({"message": "Paciente não encontrado."}), 404
        
    # LÓGICA DE CÁLCULO DE VALOR
    valor_total_calculado = 0
    procedimentos_selecionados = []
    
    # Itera sobre IDs enviados para somar valores e buscar objetos
    for proc_id in data['procedure_ids']:
        procedimento = Procedure.query.get(proc_id)
        if not procedimento:
            return jsonify({"message": f"Procedimento com ID {proc_id} não encontrado."}), 404
        procedimentos_selecionados.append(procedimento)
        
        # Usa o valor correto dependendo do tipo de atendimento
        if data['tipo'] == 'plano':
            valor_total_calculado += procedimento.valor_plano_saude
        else: 
            valor_total_calculado += procedimento.valor_particular
            
    try:
        data_atendimento = datetime.datetime.strptime(data['data_atendimento'], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return jsonify({"message": "Formato de data inválido. Use AAAA-MM-DD HH:MM:SS."}), 400
        
    # Cria o atendimento
    novo_atendimento = Appointment(
        data_atendimento=data_atendimento,
        paciente_id=data['paciente_id'],
        tipo=data['tipo'],
        numero_carteira_plano=data.get('numero_carteira_plano'),
        usuario_id=current_user.id, # Registra qual usuário do sistema criou o atendimento
        valor_total=valor_total_calculado # Salva o valor calculado pelo backend (mais seguro)
    )
    # Adiciona os relacionamentos N:N
    novo_atendimento.procedures.extend(procedimentos_selecionados)
    
    db.session.add(novo_atendimento)
    db.session.commit()
    return jsonify(novo_atendimento.to_json()), 201

@api.route('/appointments', methods=['GET'])
@token_required
def get_appointments(current_user):
    """Lista atendimentos ordenados por data (mais recente primeiro)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    pagination = Appointment.query.order_by(Appointment.data_atendimento.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    atendimentos_da_pagina = pagination.items
    return jsonify({
        'atendimentos': [appointment.to_json() for appointment in atendimentos_da_pagina],
        'total_atendimentos': pagination.total,
        'total_paginas': pagination.pages,
        'pagina_atual': pagination.page
    })

@api.route('/appointments/<int:appointment_id>', methods=['GET'])
@token_required
def get_appointment(current_user, appointment_id):
    atendimento = Appointment.query.get_or_404(appointment_id)
    return jsonify(atendimento.to_json())

@api.route('/appointments/<int:appointment_id>', methods=['PUT'])
@token_required
def update_appointment(current_user, appointment_id):
    # Atualiza atendimento e recalcula valores se necessário.
    atendimento = Appointment.query.get_or_404(appointment_id)
    
    # Permissão: Só quem criou ou admin pode alterar
    if atendimento.usuario_id != current_user.id and current_user.tipo != 'admin':
        return jsonify({'message': 'Acesso não autorizado para alterar este atendimento.'}), 403
        
    data = request.get_json()
    if 'data_atendimento' in data:
        try:
            atendimento.data_atendimento = datetime.datetime.strptime(data['data_atendimento'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return jsonify({"message": "Formato de data inválido. Use AAAA-MM-DD HH:MM:SS."}), 400
            
    atendimento.tipo = data.get('tipo', atendimento.tipo)
    atendimento.numero_carteira_plano = data.get('numero_carteira_plano', atendimento.numero_carteira_plano)
    
    # Se mudar os procedimentos, precisa recalcular o valor total
    if 'procedure_ids' in data:
        if not isinstance(data['procedure_ids'], list) or len(data['procedure_ids']) == 0:
            return jsonify({"message": "O atendimento precisa ter pelo menos um procedimento."}), 400
            
        valor_total_calculado = 0
        novos_procedimentos = []
        for proc_id in data['procedure_ids']:
            procedimento = Procedure.query.get(proc_id)
            if not procedimento:
                return jsonify({"message": f"Procedimento com ID {proc_id} não encontrado."}), 404
            novos_procedimentos.append(procedimento)
            
            # Recálculo
            if atendimento.tipo == 'plano':
                valor_total_calculado += procedimento.valor_plano_saude
            else: 
                valor_total_calculado += procedimento.valor_particular
        
        atendimento.procedures = novos_procedimentos
        atendimento.valor_total = valor_total_calculado
        
    db.session.commit()
    return jsonify(atendimento.to_json()), 200

@api.route('/appointments/<int:appointment_id>', methods=['DELETE'])
@token_required
def delete_appointment(current_user, appointment_id):
    atendimento = Appointment.query.get_or_404(appointment_id)
    
    # Permissão: Só quem criou ou admin pode remover
    if atendimento.usuario_id != current_user.id and current_user.tipo != 'admin':
        return jsonify({'message': 'Acesso não autorizado para remover este atendimento.'}), 403
        
    db.session.delete(atendimento)
    db.session.commit()
    return jsonify({'message': 'Atendimento removido com sucesso.'}), 200

@api.route('/appointments/by-date', methods=['GET'])
@token_required
def get_appointments_by_date(current_user):
    """Filtro de relatório: busca atendimentos entre duas datas."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if not start_date_str or not end_date_str:
        return jsonify({"message": "Os parâmetros 'start_date' e 'end_date' são obrigatórios."}), 400

    try:
        # Converte apenas para Data (Date), ignorando hora
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"message": "Formato de data inválido. Use AAAA-MM-DD."}), 400

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    # Filtro SQL WHERE data >= start AND data <= end
    pagination = Appointment.query.filter(
        Appointment.data_atendimento >= start_date,
        Appointment.data_atendimento <= end_date
    ).order_by(Appointment.data_atendimento.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    atendimentos_da_pagina = pagination.items

    return jsonify({
        'atendimentos': [appointment.to_json() for appointment in atendimentos_da_pagina],
        'total_atendimentos': pagination.total,
        'total_paginas': pagination.pages,
        'pagina_atual': pagination.page
    })

# --- ROTAS EXTRAS DE USUÁRIO ---

@api.route('/users/change-password', methods=['PUT'])
@token_required
def change_password(current_user):
    """Permite que o usuário logado troque sua própria senha."""
    data = request.get_json()
    senha_antiga = data.get('senha_antiga')
    senha_nova = data.get('senha_nova')

    if not senha_antiga or not senha_nova:
        return jsonify({'message': 'Senha antiga e nova são obrigatórias.'}), 400

    # Verifica se ele sabe a senha atual antes de trocar
    if not current_user.check_password(senha_antiga):
        return jsonify({'message': 'Senha antiga incorreta.'}), 401

    current_user.set_password(senha_nova)
    db.session.commit()

    return jsonify({'message': 'Senha alterada com sucesso.'}), 200

@api.route('/users/reset-password/<int:user_id>', methods=['PUT'])
@token_required
@admin_required
def admin_reset_password(current_user, user_id):
    """Admin reseta a senha de qualquer usuário (útil se o usuário esquecer a senha)."""
    data = request.get_json()
    senha_nova = data.get('senha_nova')

    if not senha_nova:
        return jsonify({'message': 'Nova senha é obrigatória.'}), 400

    user_to_reset = User.query.get_or_404(user_id)
    
    user_to_reset.set_password(senha_nova)
    db.session.commit()

    return jsonify({'message': f'Senha do usuário {user_to_reset.nome} foi resetada com sucesso.'}), 200

@api.route('/users/by-email', methods=['GET'])
@token_required
def get_user_by_email(current_user):
    # Busca usuário específico por email.
    email = request.args.get('email')
    if not email:
        return jsonify({'message': 'Parâmetro "email" é obrigatório.'}), 400

    # Só Admin pode buscar qualquer um. Usuário comum só pode buscar a si mesmo.
    if current_user.tipo != 'admin' and current_user.email != email:
        return jsonify({'message': 'Acesso não autorizado.'}), 403

    user = User.query.filter_by(email=email).first_or_404()
    
    return jsonify(user.to_json())

@api.route('/users', methods=['GET'])
@token_required
@admin_required
def get_users(current_user):
    #Lista todos os usuários do sistema (apenas Admin).
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    pagination = User.query.paginate(page=page, per_page=per_page, error_out=False)
    users_da_pagina = pagination.items

    return jsonify({
        'usuarios': [user.to_json() for user in users_da_pagina],
        'total_usuarios': pagination.total,
        'total_paginas': pagination.pages,
        'pagina_atual': pagination.page
    })