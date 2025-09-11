from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()

senha_plana = 'admin123'

hash_gerado = bcrypt.generate_password_hash(senha_plana).decode('utf-8')

print(f"Sua senha de admin será: {senha_plana}")
print(f"Seu HASH para o banco de dados é:")
print(hash_gerado)