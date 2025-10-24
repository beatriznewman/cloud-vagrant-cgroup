# 🌐 Gerenciador de Ambientes com cgroups v2

Um sistema web para gerenciar ambientes isolados usando cgroups v2 e namespaces do Linux, desenvolvido em Flask.

## 📋 Funcionalidades

- **Criação de ambientes isolados** com namespaces completos
- **Limitação de CPU** por porcentagem usando cgroups v2
- **Execução de comandos** em ambientes isolados
- **Monitoramento em tempo real** dos limites de CPU aplicados
- **Interface web intuitiva** para gerenciamento
- **Banco de dados MySQL** para persistência dos dados

## 🛠️ Tecnologias Utilizadas

- **Backend**: Python Flask
- **Banco de dados**: MySQL
- **Containerização**: Vagrant + VirtualBox
- **Isolamento**: Linux cgroups v2 + namespaces
- **Frontend**: HTML/CSS/JavaScript

## 🚀 Instalação e Configuração

### Pré-requisitos

- Vagrant
- VirtualBox
- Git

### Configuração do Ambiente

1. **Clone o repositório**:
```bash
git clone <url-do-repositorio>
cd cloud-vagrant-cgroup
```

2. **Inicie a máquina virtual**:
```bash
vagrant up
```

3. **Acesse a máquina virtual**:
```bash
vagrant ssh
```

4. **Inicie o servidor Flask**:
```bash
cd /vagrant
python3 app.py
```

5. **Acesse a aplicação**:
   - Abra o navegador em `http://localhost:5000`

## 📖 Como Usar

### Criando um Ambiente

1. Na página principal, preencha o formulário "Criar novo ambiente":
   - **Nome**: Nome do ambiente (opcional, será gerado automaticamente se vazio)
   - **CPUs**: Número de CPUs (padrão: 1)
   - **Memória**: Quantidade de memória (padrão: 512M)
   - **Limite de CPU (%)**: Porcentagem máxima de CPU (padrão: 100%)

2. Clique em "Criar"

### Executando Comandos

1. Na lista de ambientes, clique em "Ver" no ambiente desejado
2. Digite o comando a ser executado no campo de texto
3. Clique em "Executar"
4. Use "Ver saída" para acompanhar o output do comando

### Limitando CPU

- **Na criação**: Defina a porcentagem no formulário de criação
- **Após criação**: Use o campo "Limite CPU (%)" na tabela de ambientes

### Monitoramento

- A coluna "Limite Atual" mostra o limite de CPU aplicado em tempo real
- Valores possíveis: "50%", "100%", "ilimitado", "N/A"

## 🏗️ Arquitetura

### Estrutura do Projeto

```
cloud-vagrant-cgroup/
├── app.py                 # Aplicação Flask principal
├── vagrantfile           # Configuração do Vagrant
├── templates/            # Templates HTML
│   ├── index.html        # Página principal
│   ├── ambiente.html     # Página do ambiente
│   └── output.html       # Página de saída
└── README.md            # Este arquivo
```

### Componentes Principais

#### Backend (app.py)

- **`criar_cgroup(nome)`**: Cria cgroup com controladores habilitados
- **`limitar_cpu_porcentagem(nome, porcentagem)`**: Aplica limitação de CPU
- **`obter_limite_cpu(nome)`**: Lê limite atual do cgroup
- **`remover_cgroup(nome)`**: Remove cgroup e mata processos

#### Isolamento

- **Namespaces**: PID, filesystem, network, user, IPC, mount
- **cgroups v2**: Controle de recursos (CPU, memória)
- **Comando de execução**: `unshare -p -f -n -m -u -i --mount-proc`

### Banco de Dados

Tabela `ambientes`:
- `nome`: Nome do ambiente (PK)
- `cpu`: Número de CPUs
- `memoria`: Quantidade de memória
- `status`: Status atual (criado, em execução, encerrado)
- `pid`: PID do processo principal
- `output`: Caminho do arquivo de saída

## 🔧 Configuração Técnica

### cgroups v2

O sistema usa cgroups v2 para controle de recursos:

- **Controlador CPU**: Habilitado no root antes da criação de subgrupos
- **Arquivo cpu.max**: Formato `quota period` (ex: "50000 100000" = 50%)
- **Permissões**: Configuradas para www-data (775)

### Namespaces

Cada ambiente executa com namespaces isolados:

- **PID**: Processos isolados
- **Filesystem**: Sistema de arquivos isolado
- **Network**: Rede isolada
- **User**: Usuários isolados
- **IPC**: Comunicação interprocesso isolada
- **Mount**: Pontos de montagem isolados

## 🐛 Solução de Problemas

### cpu.max não é criado

**Problema**: O arquivo `cpu.max` não aparece no cgroup.

**Solução**: Verifique se o controlador `cpu` está habilitado no cgroup pai:
```bash
cat /sys/fs/cgroup/cgroup.subtree_control
```

### Permissões negadas

**Problema**: Erro de permissão ao criar cgroups.

**Solução**: Execute com sudo ou verifique se o usuário está no grupo www-data:
```bash
sudo usermod -a -G www-data $USER
```

### Comandos não executam

**Problema**: Comandos não são executados nos ambientes.

**Solução**: Verifique se o comando existe e se as permissões estão corretas:
```bash
which stress  # Para o comando stress
```

## 📝 Exemplos de Uso

### Teste de CPU com stress

1. Crie um ambiente com limite de 50% de CPU
2. Execute: `stress --cpu 1 --timeout 30s`
3. Monitore o uso de CPU com `htop`

### Teste de memória

1. Crie um ambiente com 256M de memória
2. Execute: `stress --vm 1 --vm-bytes 200M --timeout 30s`

### Comandos personalizados

- `sleep 10` - Aguarda 10 segundos
- `dd if=/dev/zero of=/tmp/test bs=1M count=100` - Teste de I/O
- `ping -c 5 8.8.8.8` - Teste de rede

## 🤝 Contribuição

1. Fork o projeto
2. Crie uma branch para sua feature (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add some AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 👥 Autores

- **Luigi Menezes** - Desenvolvimento inicial

## 📚 Referências

- [cgroups v2 Documentation](https://www.kernel.org/doc/Documentation/cgroup-v2.txt)
- [Linux Namespaces](https://man7.org/linux/man-pages/man7/namespaces.7.html)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Vagrant Documentation](https://www.vagrantup.com/docs)
