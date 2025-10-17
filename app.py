from flask import Flask, render_template, request, redirect, url_for
import subprocess
import os
import uuid
import psutil
import signal
import mysql.connector

app = Flask(__name__)

# Configuração do banco MySQL
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "projeto2_user",
    "password": "1234",
    "database": "projeto2_db",
    "connect_timeout": 5
}

# Função auxiliar para conectar ao banco
def conectar():
    return mysql.connector.connect(**DB_CONFIG)

# Criação automática da tabela se não existir
def criar_tabela():
    con = conectar()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ambientes (
            nome VARCHAR(50) PRIMARY KEY,
            cpu INT,
            memoria VARCHAR(20),
            status VARCHAR(30),
            pid INT,
            output VARCHAR(200)
        )
    """)
    con.commit()
    cur.close()
    con.close()

@app.route("/")
def home():
    criar_tabela()

    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM ambientes")
    ambientes = cur.fetchall()
    cur.close()
    con.close()
    return render_template("index.html", ambientes=ambientes)

@app.route("/criar", methods=["POST"])
def criar_ambiente():
    nome = request.form.get("nome") or f"amb_{uuid.uuid4().hex[:6]}"
    cpu = request.form.get("cpu", 1)
    memoria = request.form.get("memoria", "512M")
    status = "criado"

    caminho = f"/tmp/{nome}"
    os.makedirs(caminho, exist_ok=True)
    output = f"{caminho}/output.txt"

    con = conectar()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO ambientes (nome, cpu, memoria, status, pid, output)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (nome, cpu, memoria, status, None, output))
    con.commit()
    cur.close()
    con.close()

    return redirect(url_for("home"))

@app.route("/ambiente/<nome>")
def ver_ambiente(nome):
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM ambientes WHERE nome = %s", (nome,))
    ambiente = cur.fetchone()
    cur.close()
    con.close()

    if not ambiente:
        return "Ambiente não encontrado", 404

    pid = ambiente["pid"]
    if pid and psutil.pid_exists(pid):
        ambiente["status"] = "em execução"
    elif pid:
        ambiente["status"] = "terminado"

    # Atualiza status no banco
    con = conectar()
    cur = con.cursor()
    cur.execute("UPDATE ambientes SET status = %s WHERE nome = %s", (ambiente["status"], nome))
    con.commit()
    cur.close()
    con.close()

    return render_template("ambiente.html", ambiente=ambiente)

@app.route("/executar/<nome>", methods=["POST"])
def executar_programa(nome):
    comando = request.form.get("comando")

    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM ambientes WHERE nome = %s", (nome,))
    ambiente = cur.fetchone()
    cur.close()
    con.close()

    if not ambiente:
        return "Ambiente não encontrado", 404

    saida = ambiente["output"]
    with open(saida, "w") as f:
        processo = subprocess.Popen(comando, shell=True, stdout=f, stderr=f, preexec_fn=os.setsid)
        pid = processo.pid

    con = conectar()
    cur = con.cursor()
    cur.execute("UPDATE ambientes SET pid = %s, status = %s WHERE nome = %s", (pid, "em execução", nome))
    con.commit()
    cur.close()
    con.close()

    return redirect(url_for("ver_ambiente", nome=nome))

@app.route("/output/<nome>")
def ver_output(nome):
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT output FROM ambientes WHERE nome = %s", (nome,))
    amb = cur.fetchone()
    cur.close()
    con.close()

    if not amb:
        return "Ambiente não encontrado", 404

    arquivo = amb["output"]
    conteudo = ""
    if os.path.exists(arquivo):
        with open(arquivo) as f:
            conteudo = f.read()

    return render_template("output.html", nome=nome, conteudo=conteudo)

@app.route("/encerrar/<nome>", methods=["POST"])
def encerrar_ambiente(nome):
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT pid FROM ambientes WHERE nome = %s", (nome,))
    amb = cur.fetchone()
    cur.close()

    if amb and amb["pid"]:
        pid = amb["pid"]
        if psutil.pid_exists(pid):
            os.killpg(os.getpgid(pid), signal.SIGTERM)

    cur = con.cursor()
    cur.execute("UPDATE ambientes SET status = %s WHERE nome = %s", ("encerrado", nome))
    con.commit()
    cur.close()
    con.close()

    return redirect(url_for("home"))

@app.route("/remover/<nome>", methods=["POST"])
def remover_ambiente(nome):
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT output FROM ambientes WHERE nome = %s", (nome,))
    amb = cur.fetchone()
    cur.close()

    if amb:
        caminho = os.path.dirname(amb["output"])
        subprocess.call(["rm", "-rf", caminho])

    cur = con.cursor()
    cur.execute("DELETE FROM ambientes WHERE nome = %s", (nome,))
    con.commit()
    cur.close()
    con.close()

    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
