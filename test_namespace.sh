#!/bin/bash
# =======================================================
# Teste de Namespaces e Isolamento de Ambientes
# Projeto 2 - Sistemas Operacionais
# Uso: sudo ./test_namespace.sh <nome_do_ambiente>
# =======================================================

AMBIENTE=$1
CGROUP_PATH="/sys/fs/cgroup/$AMBIENTE"

# -------------------------------------------------------
# Verificações iniciais
# -------------------------------------------------------
if [ -z "$AMBIENTE" ]; then
    echo "❌ Uso: sudo $0 <nome_do_ambiente>"
    exit 1
fi

if [ ! -d "$CGROUP_PATH" ]; then
    echo "❌ Cgroup $AMBIENTE não encontrado em $CGROUP_PATH"
    exit 1
fi

echo "🔍 Verificando processos do ambiente '$AMBIENTE'..."
PIDS=$(cat "$CGROUP_PATH/cgroup.procs" 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "❌ Nenhum processo encontrado no cgroup!"
    exit 1
fi

PID=$(echo "$PIDS" | head -n1)
echo "✅ Usando PID principal: $PID"
echo

# -------------------------------------------------------
# Informações de namespaces
# -------------------------------------------------------
echo "=============================="
echo "📂 NAMESPACES DO PROCESSO"
echo "=============================="
sudo readlink /proc/$PID/ns/*

echo
echo "=============================="
echo "🔍 COMPARAÇÃO COM O HOST"
echo "=============================="
echo "PID namespace (host vs ambiente):"
echo "Host: $(sudo readlink /proc/1/ns/pid)"
echo "Amb : $(sudo readlink /proc/$PID/ns/pid)"
echo
echo "UTS namespace (hostname):"
echo "Host: $(hostname)"
echo "Amb : $(sudo nsenter -t $PID -u hostname)"
echo
echo "Processos visíveis dentro do namespace:"
sudo nsenter -t $PID -p ps -ef
echo

# -------------------------------------------------------
# Testes de recursos via Cgroups
# -------------------------------------------------------
echo "=============================="
echo "⚙️  TESTE DE LIMITES DE RECURSOS (Cgroups v2)"
echo "=============================="

# CPU
echo
echo "🧮 CPU:"
if [ -f "$CGROUP_PATH/cpu.max" ]; then
    CPU_MAX=$(cat "$CGROUP_PATH/cpu.max")
    echo "  • Limite configurado (cpu.max): $CPU_MAX"
else
    echo "  • Arquivo cpu.max não encontrado"
fi

if [ -f "$CGROUP_PATH/cpu.stat" ]; then
    echo "  • Estatísticas atuais (cpu.stat):"
    cat "$CGROUP_PATH/cpu.stat" | sed 's/^/    - /'
else
    echo "  • Arquivo cpu.stat não encontrado"
fi

# Memória
echo
echo "🧠 MEMÓRIA:"
if [ -f "$CGROUP_PATH/memory.max" ]; then
    MEM_MAX=$(cat "$CGROUP_PATH/memory.max")
    echo "  • Limite configurado (memory.max): $MEM_MAX"
else
    echo "  • Arquivo memory.max não encontrado"
fi

if [ -f "$CGROUP_PATH/memory.current" ]; then
    MEM_CUR=$(cat "$CGROUP_PATH/memory.current")
    echo "  • Uso atual (memory.current): $MEM_CUR bytes"
    if [ "$MEM_MAX" != "max" ]; then
        PCT=$(( 100 * MEM_CUR / MEM_MAX ))
        echo "  • Uso relativo: ${PCT}%"
    fi
else
    echo "  • Arquivo memory.current não encontrado"
fi

# I/O
echo
echo "💾 I/O:"
if [ -f "$CGROUP_PATH/io.max" ]; then
    echo "  • Limite configurado (io.max):"
    cat "$CGROUP_PATH/io.max" | sed 's/^/    - /'
else
    echo "  • Arquivo io.max não encontrado"
fi

if [ -f "$CGROUP_PATH/io.stat" ]; then
    echo "  • Estatísticas de I/O (io.stat):"
    cat "$CGROUP_PATH/io.stat" | sed 's/^/    - /'
else
    echo "  • Arquivo io.stat não encontrado"
fi

# CPUs designadas (se cpuset estiver habilitado)
if [ -f "$CGROUP_PATH/cpuset.cpus" ]; then
    echo
    echo "🧩 CPUSET:"
    echo "  • CPUs permitidas: $(cat $CGROUP_PATH/cpuset.cpus)"
fi

# -------------------------------------------------------
# Sumário de isolamento
# -------------------------------------------------------
echo
echo "=============================="
echo "📊 SUMÁRIO FINAL"
echo "=============================="
PID_ISO=$( [ "$(sudo readlink /proc/1/ns/pid)" != "$(sudo readlink /proc/$PID/ns/pid)" ] && echo "SIM" || echo "NÃO" )
UTS_ISO=$( [ "$(hostname)" != "$(sudo nsenter -t $PID -u hostname)" ] && echo "SIM" || echo "NÃO" )
NET_ISO=$( sudo nsenter -t $PID -n ip link show | grep -q eth0 && echo "NÃO" || echo "SIM" )

echo "PID isolado?  $PID_ISO"
echo "UTS isolado?  $UTS_ISO"
echo "Rede isolada? $NET_ISO"

if [ -f "$CGROUP_PATH/memory.max" ]; then
    echo "Limite de Memória: $(cat $CGROUP_PATH/memory.max)"
fi

if [ -f "$CGROUP_PATH/cpu.max" ]; then
    echo "Limite de CPU: $(cat $CGROUP_PATH/cpu.max)"
fi

echo
echo "✅ Teste completo concluído!"
