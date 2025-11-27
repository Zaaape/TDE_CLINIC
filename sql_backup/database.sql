
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    nome VARCHAR(255) NOT NULL,
    tipo VARCHAR(50) NOT NULL CHECK (tipo IN ('admin', 'default')),
    senha_hash VARCHAR(255) NOT NULL
);

CREATE TABLE patients (
    id SERIAL PRIMARY KEY,
    cpf VARCHAR(14) UNIQUE NOT NULL,
    nome VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    telefone VARCHAR(20) NOT NULL,
    data_nascimento DATE NOT NULL,
    estado VARCHAR(100) NOT NULL,
    cidade VARCHAR(100) NOT NULL,
    bairro VARCHAR(100) NOT NULL,
    cep VARCHAR(10) NOT NULL,
    rua VARCHAR(255) NOT NULL,
    numero VARCHAR(20) NOT NULL,
    responsavel_cpf VARCHAR(14),
    responsavel_nome VARCHAR(255),
    responsavel_data_nascimento DATE,
    responsavel_email VARCHAR(255),
    responsavel_telefone VARCHAR(20)
);

CREATE TABLE procedures (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) UNIQUE NOT NULL,
    descricao TEXT,
    valor_plano_saude NUMERIC(10, 2) NOT NULL,
    valor_particular NUMERIC(10, 2) NOT NULL
);

CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    data_atendimento TIMESTAMP NOT NULL,
    paciente_id INTEGER NOT NULL REFERENCES patients(id),
    tipo VARCHAR(50) NOT NULL CHECK (tipo IN ('plano', 'particular')),
    numero_carteira_plano VARCHAR(100),
    usuario_id INTEGER NOT NULL REFERENCES users(id),
    valor_total NUMERIC(10, 2) NOT NULL
);

CREATE TABLE appointment_procedures (
    appointment_id INTEGER NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    procedure_id INTEGER NOT NULL REFERENCES procedures(id),
    PRIMARY KEY (appointment_id, procedure_id)
);

INSERT INTO users (email, nome, tipo, senha_hash) VALUES
('admin@clinic.com', 'Administrador', 'admin', 'bcrypt_hash_para_123456'),
('user@clinic.com', 'Usuário Padrão', 'default', 'bcrypt_hash_para_123456');

INSERT INTO patients (cpf, nome, email, telefone, data_nascimento, estado, cidade, bairro, cep, rua, numero) VALUES
('111.222.333-44', 'João da Silva', 'joao.silva@example.com', '75999998888', '1990-05-15', 'Bahia', 'Feira de Santana', 'Centro', '44001-000', 'Rua A', '123');

INSERT INTO patients (cpf, nome, email, telefone, data_nascimento, estado, cidade, bairro, cep, rua, numero, responsavel_cpf, responsavel_nome, responsavel_data_nascimento, responsavel_email, responsavel_telefone) VALUES
('555.666.777-88', 'Ana Clara', 'ana.clara@example.com', '75988887777', '2015-10-20', 'Bahia', 'Feira de Santana', 'SIM', '44088-000', 'Rua B', '456', '999.888.777-66', 'Maria Souza (Mãe)', '1985-02-25', 'maria.souza@example.com', '75977776666');

INSERT INTO procedures (nome, descricao, valor_plano_saude, valor_particular) VALUES
('Consulta Médica', 'Consulta de rotina com clínico geral.', 150.00, 250.00),
('Limpeza Dentária', 'Procedimento de limpeza e profilaxia.', 80.00, 120.00),
('Exame de Sangue', 'Coleta e análise de sangue.', 50.00, 90.00);

INSERT INTO appointments (data_atendimento, paciente_id, tipo, numero_carteira_plano, usuario_id, valor_total) VALUES
('2025-08-20 10:00:00', 1, 'plano', '123456789-01', 1, 150.00);

INSERT INTO appointment_procedures (appointment_id, procedure_id) VALUES
(1, 1);
