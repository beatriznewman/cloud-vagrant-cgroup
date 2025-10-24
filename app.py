from flask import Flask, render_template, request, redirect, url_for
import subprocess
import os
import uuid
import psutil
import signal
import mysql.connector

app = Flask(__name__)

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "projeto2_user",
    "password": "1234",
    "database": "projeto2_db",
    "connect_timeout": 5
}

def conectar():
    return mysql.connector.connect(**DB_CONFIG)

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

# Função para criar o diretório do cgroup
def criar_cgroup(nome):
    cgroup_path = f"/sys/fs/cgroup/{nome}"
    os.makedirs(cgroup_path, exist_ok=True)
    # Ativa controladores
    subprocess.run(["bash", "-c", f"echo '+cpu' > /sys/fs/cgroup/cgroup.subtree_control"], stderr=subprocess.DEVNULL)
    return cgroup_path

# Função para limitar CPU por porcentagem (ex: 50%)
def limitar_cpu_porcentagem(nome, porcentagem):
    cgroup_path = f"/sys/fs/cgroup/{nome}"
    if not os.path.exists(cgroup_path):
        return f"Cgroup {nome} não existe"

    period = 100000  # período padrão (100ms)
    if porcentagem == "max":
        quota = "max"
    else:
        porcentagem = int(porcentagem)
        quota = int(period * (porcentagem / 100))

    with open(f"{cgroup_path}/cpu.max", "w") as f:
        f.write(f"{quota} {period}\n")

    return f"Limite de CPU definido: {porcentagem}%"

def listar_comandos_ativos():
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT nome, output, status FROM ambientes WHERE status = 'em execução'")
    ambientes = cur.fetchall()
    cur.close()
    con.close()

    comandos = []
    for amb in ambientes:
        if os.path.exists(amb["output"]):
            with open(amb["output"]) as f:
                conteudo = f.read().strip()
                if conteudo:
                    comandos.append({"nome": amb["nome"], "conteudo": conteudo})
    return comandos


@app.route("/")
def home():
    criar_tabela()
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM ambientes")
    ambientes = cur.fetchall()
    cur.close()
    con.close()
    comandos = listar_comandos_ativos()
    return render_template("index.html", ambientes=ambientes, comandos=comandos)


@app.route("/criar", methods=["POST"])
def criar_ambiente():
    nome = request.form.get("nome") or f"amb_{uuid.uuid4().hex[:6]}"
    cpu = request.form.get("cpu", 1)
    memoria = request.form.get("memoria", "512M")
    status = "criado"

    caminho = f"/tmp/{nome}"
    os.makedirs(caminho, exist_ok=True)
    output = f"{caminho}/output.txt"

    # Cria o cgroup correspondente
    criar_cgroup(nome)

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

@app.route("/executar/<nome>", methods=["POST"])
def executar_programa(nome):
    comando = request.form.get("comando", "stress --cpu 1")

    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT * FROM ambientes WHERE nome = %s", (nome,))
    ambiente = cur.fetchone()
    cur.close()
    con.close()

    if not ambiente:
        return "Ambiente não encontrado", 404

    saida = ambiente["output"]
    cgroup_path = f"/sys/fs/cgroup/{nome}"

    # comando com unshare + namespace de PID + associação ao cgroup
    cmd = f"sudo unshare -p -f --mount-proc bash -c 'echo $$ > {cgroup_path}/cgroup.procs && {comando}'"

    with open(saida, "w") as f:
        processo = subprocess.Popen(cmd, shell=True, stdout=f, stderr=f, preexec_fn=os.setsid)
        pid = processo.pid

    con = conectar()
    cur = con.cursor()
    cur.execute("UPDATE ambientes SET pid = %s, status = %s WHERE nome = %s", (pid, "em execução", nome))
    con.commit()
    cur.close()
    con.close()

    return redirect(url_for("ver_ambiente", nome=nome))

@app.route("/limitar_cpu/<nome>", methods=["POST"])
def limitar_cpu(nome):
    porcentagem = request.form.get("porcentagem")
    msg = limitar_cpu_porcentagem(nome, porcentagem)
    return redirect(url_for("ver_ambiente", nome=nome))

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
