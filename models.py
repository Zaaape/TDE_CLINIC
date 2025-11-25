from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt

# Inicializa as extensões.
# Bcrypt: Biblioteca especializada em criptografia segura de senhas.

db = SQLAlchemy()
bcrypt = Bcrypt()

# TABELA ASSOCIATIVA 
# Esta tabela não é uma classe (Model) completa porque ela serve apenas para ligar
# 'appointments' (atendimentos) e 'procedures' (procedimentos). 
appointment_procedures = db.Table('appointment_procedures',
    db.Column('appointment_id', db.Integer, db.ForeignKey('appointments.id'), primary_key=True),
    db.Column('procedure_id', db.Integer, db.ForeignKey('procedures.id'), primary_key=True)
)

# --- MODELO DE USUÁRIO (LOGIN) ---
class User(db.Model):
    __tablename__ = 'users' # Nome real da tabela no banco de dados

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False) # unique=True impede emails repetidos
    nome = db.Column(db.String(255), nullable=False)
    # Define se é 'admin' ou 'default'. O padrão é 'default'.
    tipo = db.Column(db.String(50), nullable=False, default='default')
    # ATENÇÃO: Nunca salvamos a senha real. Salvamos apenas o HASH (senha criptografada).
    senha_hash = db.Column(db.String(255), nullable=False)

    # Método para definir a senha.
    # Ele pega a senha em texto plano ('123456'), gera um hash seguro e salva no objeto.
    def set_password(self, senha):
        self.senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

    # Método para verificar login.
    # Ele compara a senha que o usuário digitou agora com o hash salvo no banco.
    def check_password(self, senha):
        return bcrypt.check_password_hash(self.senha_hash, senha)

    # Converte o objeto do banco para um Dicionário Python (JSON).
    # Útil para a API retornar os dados para o front-end ou aplicativos móveis.
    def to_json(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "email": self.email,
            "tipo": self.tipo
            # Nota: Nunca retornamos a senha ou o hash no JSON por segurança.
        }

# --- MODELO DE PACIENTE ---
class Patient(db.Model):
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True)
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    nome = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    telefone = db.Column(db.String(20), nullable=False)
    data_nascimento = db.Column(db.Date, nullable=False)
    
    # Dados de Endereço
    estado = db.Column(db.String(100), nullable=False)
    cidade = db.Column(db.String(100), nullable=False)
    bairro = db.Column(db.String(100), nullable=False)
    cep = db.Column(db.String(10), nullable=False)
    rua = db.Column(db.String(255), nullable=False)
    numero = db.Column(db.String(20), nullable=False)
    
    # Dados do Responsável (Opcionais - nullable=True padrão do SQLAlchemy se não especificar False)
    # Só serão preenchidos se o paciente for menor de idade (lógica controlada no routes.py)
    responsavel_cpf = db.Column(db.String(14))
    responsavel_nome = db.Column(db.String(255))
    responsavel_data_nascimento = db.Column(db.Date)
    responsavel_email = db.Column(db.String(255))
    responsavel_telefone = db.Column(db.String(20))

    def to_json(self):
        # Formata a estrutura para ser consumida facilmente por quem chamar a API
        return {
            "id": self.id,
            "cpf": self.cpf,
            "nome": self.nome,
            "email": self.email,
            "telefone": self.telefone,
            # Converte objeto Date para string 'AAAA-MM-DD'
            "data_nascimento": self.data_nascimento.strftime('%Y-%m-%d') if self.data_nascimento else None,
            "endereco": {
                "estado": self.estado,
                "cidade": self.cidade,
                "bairro": self.bairro,
                "cep": self.cep,
                "rua": self.rua,
                "numero": self.numero
            },
            # Retorna objeto responsavel apenas se existir (operador ternário)
            "responsavel": {
                "cpf": self.responsavel_cpf,
                "nome": self.responsavel_nome,
                "data_nascimento": self.responsavel_data_nascimento.strftime('%Y-%m-%d') if self.responsavel_data_nascimento else None,
                "email": self.responsavel_email,
                "telefone": self.responsavel_telefone
            } if self.responsavel_cpf else None
        }

# --- MODELO DE PROCEDIMENTO ---
class Procedure(db.Model):
    __tablename__ = 'procedures'

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(255), unique=True, nullable=False)
    descricao = db.Column(db.Text, nullable=True) # Campo de texto longo opcional
    
    # Usamos Numeric para dinheiro para evitar erros de arredondamento de Float
    valor_plano_saude = db.Column(db.Numeric(10, 2), nullable=False)
    valor_particular = db.Column(db.Numeric(10, 2), nullable=False)

    # Relacionamento Reverso: Permite acessar todos os agendamentos que usaram este procedimento.
    # 'secondary' aponta para a tabela associativa criada no topo do arquivo.
    appointments = db.relationship('Appointment', secondary=appointment_procedures, back_populates='procedures')

    def to_json(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
            # Convertemos Numeric para string para preservar precisão decimal no JSON
            "valor_plano_saude": str(self.valor_plano_saude),
            "valor_particular": str(self.valor_particular)
        }

# --- MODELO DE ATENDIMENTO (O HUB CENTRAL) ---
class Appointment(db.Model):
    __tablename__ = 'appointments'
    
    id = db.Column(db.Integer, primary_key=True)
    data_atendimento = db.Column(db.TIMESTAMP, nullable=False)
    
    # Chave Estrangeira (ForeignKey): Liga este agendamento a um Paciente existente
    paciente_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    
    tipo = db.Column(db.String(50), nullable=False) # 'plano' ou 'particular'
    numero_carteira_plano = db.Column(db.String(100)) # Opcional, só se tipo == 'plano'
    
    # Chave Estrangeira: Liga ao Usuário (Funcionário) que criou o agendamento
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    valor_total = db.Column(db.Numeric(10, 2), nullable=False)
    
    # --- RELACIONAMENTOS (ORM) ---
    # Estes atributos não existem no banco como colunas, são "mágica" do SQLAlchemy
    # para permitir acessar os objetos relacionados diretamente no código.
    
    patient = db.relationship('Patient') # Ex: meu_agendamento.patient.nome
    user = db.relationship('User')       # Ex: meu_agendamento.user.email
    
    # Relacionamento N:N
    # Ex: meu_agendamento.procedures retorna uma lista [Procedimento A, Procedimento B]
    procedures = db.relationship('Procedure', secondary=appointment_procedures, back_populates='appointments')

    def to_json(self):
        return {
            "id": self.id,
            "data_atendimento": self.data_atendimento.strftime('%Y-%m-%d %H:%M:%S'),
            "paciente_id": self.paciente_id,
            "tipo": self.tipo,
            "numero_carteira_plano": self.numero_carteira_plano,
            "usuario_id": self.usuario_id,
            "valor_total": str(self.valor_total),
            # Inclui a lista completa dos procedimentos detalhados dentro do JSON do agendamento
            "procedimentos": [procedure.to_json() for procedure in self.procedures]
        }