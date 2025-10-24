from flask import Flask, render_template, request, redirect, url_for
import subprocess
import os
import uuid
import psutil
import signal
import mysql.connector
import time

app = Flask(__name__)

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "projeto2_user",
    "password": "1234",
    "database": "projeto2_db",
    "connect_timeout": 5
}

def conectar():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as e:
        print(f"Erro de conexão com MySQL: {e}")
        raise

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
    
    # Primeiro, habilita o controlador cpu no root ANTES de criar o subdiretório
    subprocess.run(["sudo", "bash", "-c", f"echo '+cpu' > /sys/fs/cgroup/cgroup.subtree_control"], stderr=subprocess.DEVNULL)
    
    # Cria diretório com sudo para garantir permissões
    subprocess.run(["sudo", "mkdir", "-p", cgroup_path], check=False)
    
    # Ativa controladores no subgrupo criado
    subprocess.run(["sudo", "bash", "-c", f"echo '+cpu' > {cgroup_path}/cgroup.subtree_control"], stderr=subprocess.DEVNULL)
    
    # Configura permissões para www-data
    subprocess.run(["sudo", "chown", "root:www-data", cgroup_path], stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "chmod", "775", cgroup_path], stderr=subprocess.DEVNULL)
    
    return cgroup_path

# Função para obter o limite atual de CPU do cgroup
def obter_limite_cpu(nome):
    cgroup_path = f"/sys/fs/cgroup/{nome}"
    cpu_max_file = f"{cgroup_path}/cpu.max"
    
    if not os.path.exists(cgroup_path) or not os.path.exists(cpu_max_file):
        return "N/A"
    
    try:
        with open(cpu_max_file, 'r') as f:
            content = f.read().strip()
            if content == "max 100000":
                return "100%"
            elif content.startswith("max"):
                return "ilimitado"
            else:
                # Parse do formato "quota period"
                parts = content.split()
                if len(parts) == 2:
                    quota = int(parts[0])
                    period = int(parts[1])
                    if period > 0:
                        porcentagem = (quota / period) * 100
                        return f"{porcentagem:.0f}%"
                return "N/A"
    except (ValueError, FileNotFoundError, PermissionError, ZeroDivisionError):
        return "N/A"

# Função para remover o cgroup
def remover_cgroup(nome):
    cgroup_path = f"/sys/fs/cgroup/{nome}"
    if os.path.exists(cgroup_path):
        # Mata todos os processos do cgroup usando sudo
        try:
            result = subprocess.run(["sudo", "cat", f"{cgroup_path}/cgroup.procs"], 
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid.strip():
                        try:
                            subprocess.run(["sudo", "kill", "-TERM", pid], stderr=subprocess.DEVNULL)
                        except:
                            pass
        except:
            pass
        
        # Aguarda um pouco para os processos terminarem
        time.sleep(1)
        
        # Tenta remover o diretório do cgroup
        result = subprocess.run(["sudo", "rmdir", cgroup_path], stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            # Se não conseguir remover, tenta forçar a remoção
            subprocess.run(["sudo", "rm", "-rf", cgroup_path], stderr=subprocess.DEVNULL)

# Função para limpar cgroups órfãos
def limpar_cgroups_orfos():
    """Remove cgroups que não estão mais no banco de dados"""
    con = conectar()
    cur = con.cursor()
    cur.execute("SELECT nome FROM ambientes")
    ambientes_db = [row[0] for row in cur.fetchall()]
    cur.close()
    con.close()
    
    # Lista todos os cgroups no sistema
    try:
        result = subprocess.run(["sudo", "ls", "/sys/fs/cgroup/"], 
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if result.returncode == 0:
            cgroups_sistema = result.stdout.strip().split('\n')
            for cgroup in cgroups_sistema:
                cgroup = cgroup.strip()
                # Ignora diretórios padrão do sistema
                if (cgroup and cgroup not in ambientes_db and 
                    cgroup not in ['system.slice', 'user.slice', 'init.scope'] and
                    not cgroup.endswith('.mount')):
                    print(f"Removendo cgroup órfão: {cgroup}")
                    remover_cgroup(cgroup)
    except:
        pass

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

    # Usa sudo para escrever no arquivo cpu.max
    result = subprocess.run(["sudo", "bash", "-c", f"echo '{quota} {period}' > {cgroup_path}/cpu.max"], 
                          stderr=subprocess.DEVNULL)
    
    if result.returncode == 0:
        return f"Limite de CPU definido: {porcentagem}%"
    else:
        return f"Erro ao definir limite de CPU para {nome}"

def listar_comandos_ativos():
    try:
        con = conectar()
        cur = con.cursor(dictionary=True)
        cur.execute("SELECT nome, output, status FROM ambientes WHERE status = 'em execução'")
        ambientes = cur.fetchall()
        cur.close()
        con.close()

        comandos = []
        for amb in ambientes:
            try:
                if os.path.exists(amb["output"]):
                    with open(amb["output"], 'r', encoding='utf-8', errors='ignore') as f:
                        conteudo = f.read().strip()
                        if conteudo:
                            comandos.append({"nome": amb["nome"], "conteudo": conteudo})
            except (IOError, OSError):
                # Ignora arquivos que não podem ser lidos
                pass
        return comandos
    except Exception:
        # Retorna lista vazia em caso de erro
        return []


@app.route("/")
def home():
    try:
        criar_tabela()
        
        con = conectar()
        cur = con.cursor(dictionary=True)
        cur.execute("SELECT * FROM ambientes")
        ambientes = cur.fetchall()
        cur.close()
        con.close()
        
        # Adiciona o limite atual de CPU para cada ambiente
        for ambiente in ambientes:
            ambiente['limite_atual'] = obter_limite_cpu(ambiente['nome'])
        
        comandos = listar_comandos_ativos()
        return render_template("index.html", ambientes=ambientes, comandos=comandos)
    except Exception as e:
        print(f"Erro na página principal: {e}")
        return render_template("index.html", ambientes=[], comandos=[])


@app.route("/criar", methods=["POST"])
def criar_ambiente():
    nome = request.form.get("nome") or f"amb_{uuid.uuid4().hex[:6]}"
    cpu = request.form.get("cpu", 1)
    memoria = request.form.get("memoria", "512M")
    porcentagem = request.form.get("porcentagem")
    status = "criado"

    caminho = f"/tmp/{nome}"
    os.makedirs(caminho, exist_ok=True)
    output = f"{caminho}/output.txt"

    # Cria o cgroup correspondente
    criar_cgroup(nome)
    
    # Aplica limitação de CPU se fornecida
    if porcentagem and porcentagem.strip():
        limitar_cpu_porcentagem(nome, porcentagem)

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

    # comando com unshare conforme especificação do slide
    # Cria namespace isolado primeiro, depois move o bash isolado para o cgroup
    cmd = f"sudo unshare -pf --mount-proc /bin/bash -c 'echo $$ > {cgroup_path}/cgroup.procs && exec {comando}'"
    
    print(f"🔧 Executando comando: {cmd}")
    print(f"🔧 Comando original: {comando}")

    with open(saida, "w") as f:
        processo = subprocess.Popen(cmd, shell=True, stdout=f, stderr=f, preexec_fn=os.setsid)
        pid = processo.pid

    con = conectar()
    cur = con.cursor()
    cur.execute("UPDATE ambientes SET pid = %s, status = %s WHERE nome = %s", (pid, "em execução", nome))
    con.commit()
    cur.close()
    con.close()

    # Verifica se o processo foi associado ao cgroup (logs detalhados)
    time.sleep(2)  # Aguarda o processo ser criado
    try:
        if os.path.exists(cgroup_path):
            # Verifica processos no cgroup
            result = subprocess.run(["sudo", "cat", f"{cgroup_path}/cgroup.procs"], 
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                print(f"✅ Processos no cgroup {nome}: {pids}")
                
                # Verifica o nome do processo e se está rodando
                for pid in pids:
                    if pid.strip():
                        try:
                            with open(f"/proc/{pid.strip()}/comm", 'r') as f:
                                comm = f.read().strip()
                                print(f"✅ Processo {pid.strip()} é: {comm}")
                            
                            # Verifica se o processo está realmente ativo
                            with open(f"/proc/{pid.strip()}/stat", 'r') as f:
                                stat = f.read().strip().split()
                                if len(stat) > 2:
                                    state = stat[2]  # R=running, S=sleeping, etc.
                                    print(f"✅ Processo {pid.strip()} ({comm}) estado: {state}")
                                    
                                    # Verifica uso de CPU
                                    if len(stat) > 13:
                                        utime = int(stat[13])
                                        stime = int(stat[14])
                                        total_time = utime + stime
                                        print(f"✅ Processo {pid.strip()} tempo CPU: {total_time}")
                        except Exception as e:
                            print(f"❌ Erro ao verificar processo {pid.strip()}: {e}")
                            
            else:
                print(f"❌ Nenhum processo no cgroup {nome}")
                
            # Verifica se há processos stress rodando no sistema
            try:
                result = subprocess.run(["pgrep", "-f", "stress"], 
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    stress_pids = result.stdout.strip().split('\n')
                    print(f"🔍 Processos stress encontrados no sistema: {stress_pids}")
                else:
                    print(f"❌ Nenhum processo stress encontrado no sistema")
            except:
                pass
        else:
            print(f"❌ Cgroup {nome} não existe em {cgroup_path}")
    except Exception as e:
        print(f"❌ Erro ao verificar cgroup {nome}: {e}")

    return redirect(url_for("ver_ambiente", nome=nome))

@app.route("/limitar_cpu/<nome>", methods=["POST"])
def limitar_cpu(nome):
    porcentagem = request.form.get("porcentagem")
    msg = limitar_cpu_porcentagem(nome, porcentagem)
    return redirect(url_for("home"))

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

    # Remove o cgroup ao encerrar
    remover_cgroup(nome)

    cur = con.cursor()
    cur.execute("UPDATE ambientes SET status = %s WHERE nome = %s", ("encerrado", nome))
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
    
    return render_template("ambiente.html", ambiente=ambiente)

@app.route("/remover/<nome>", methods=["POST"])
def remover_ambiente(nome):
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT pid FROM ambientes WHERE nome = %s", (nome,))
    amb = cur.fetchone()
    
    if amb and amb["pid"]:
        pid = amb["pid"]
        if psutil.pid_exists(pid):
            os.killpg(os.getpgid(pid), signal.SIGTERM)
    
    remover_cgroup(nome)
    
    cur.execute("DELETE FROM ambientes WHERE nome = %s", (nome,))
    con.commit()
    cur.close()
    con.close()
    
    return redirect(url_for("home"))

@app.route("/output/<nome>")
def ver_output(nome):
    con = conectar()
    cur = con.cursor(dictionary=True)
    cur.execute("SELECT output FROM ambientes WHERE nome = %s", (nome,))
    ambiente = cur.fetchone()
    cur.close()
    con.close()
    
    if not ambiente:
        return "Ambiente não encontrado", 404
    
    output_file = ambiente["output"]
    conteudo = ""
    if os.path.exists(output_file):
        with open(output_file, "r") as f:
            conteudo = f.read()
    
    return render_template("output.html", nome=nome, conteudo=conteudo)

@app.route("/limpar_cgroups", methods=["POST"])
def limpar_cgroups():
    """Rota para limpar cgroups órfãos manualmente"""
    limpar_cgroups_orfos()
    return redirect(url_for("home"))

@app.route("/status_cgroups")
def status_cgroups():
    """Rota para verificar status dos cgroups"""
    try:
        result = subprocess.run(["sudo", "ls", "/sys/fs/cgroup/"], 
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if result.returncode == 0:
            cgroups = result.stdout.strip().split('\n')
            status = []
            for cgroup in cgroups:
                cgroup = cgroup.strip()
                if cgroup and not cgroup.endswith('.mount') and cgroup not in ['system.slice', 'user.slice', 'init.scope']:
                    # Verifica processos no cgroup
                    proc_result = subprocess.run(["sudo", "cat", f"/sys/fs/cgroup/{cgroup}/cgroup.procs"], 
                                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                    procs = proc_result.stdout.strip() if proc_result.returncode == 0 else ""
                    
                    # Verifica limite de CPU
                    cpu_result = subprocess.run(["sudo", "cat", f"/sys/fs/cgroup/{cgroup}/cpu.max"], 
                                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                    cpu_limit = cpu_result.stdout.strip() if cpu_result.returncode == 0 else "N/A"
                    
                    status.append({
                        'nome': cgroup,
                        'processos': procs,
                        'cpu_limit': cpu_limit
                    })
            status_lines = []
            for s in status:
                status_lines.append(f"{s['nome']}: processos={s['processos']}, cpu_limit={s['cpu_limit']}")
            return f"<pre>Cgroups Status:\n{chr(10).join(status_lines)}</pre>"
        else:
            return "Erro ao listar cgroups"
    except Exception as e:
        return f"Erro: {str(e)}"
