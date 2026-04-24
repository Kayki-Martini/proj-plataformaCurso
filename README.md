# Plataforma EAD em Microservicos

Sistema completo para gestao de cursos online (EAD) com arquitetura de microservicos, API Gateway, bancos isolados por servico, frontend React + Vite + Tailwind e orquestracao com Docker Compose.

## Servicos

- `auth-service`: login, registro, JWT e roles (`admin`, `aluno`)
- `user-service`: perfil dos alunos com CPF unico
- `course-service`: catalogo e turmas com capacidade maxima de 200 alunos
- `enrollment-service`: matriculas por CPF, grupos de ate 5 alunos e janela de 5 a 1 semanas antes do inicio
- `lesson-service`: aulas em cards, com ordem obrigatoria, preco por aula e liberacao semanal
- `progress-service`: conclusao sequencial das aulas, percentual de progresso e leitura da turma por aluno
- `payment-service`: pagamentos por aula via cartao de credito
- `gateway`: roteamento central via Nginx
- `frontend`: dashboard web React

## Estrutura

```text
gateway/
services/
  auth-service/
  user-service/
  course-service/
  enrollment-service/
  lesson-service/
  progress-service/
  payment-service/
frontend/
```

## Como rodar

1. Opcionalmente copie `.env.example` para `.env` e ajuste os valores.
2. Suba toda a stack:

```bash
docker compose up --build
```

3. Acesse:

- Frontend: `http://localhost:3000`
- Gateway: `http://localhost:8080/health`
- Swagger:
  - Auth: `http://localhost:8001/docs`
  - Users: `http://localhost:8002/docs`
  - Courses: `http://localhost:8003/docs`
  - Enrollments: `http://localhost:8004/docs`
  - Lessons: `http://localhost:8005/docs`
  - Progress: `http://localhost:8006/docs`
  - Payments: `http://localhost:8007/docs`

## Fluxo sugerido

1. Registre um usuario no frontend.
2. Complete o perfil do aluno no dashboard.
3. Crie cursos e aulas no Studio Admin com um usuario `admin`.
4. Matricule o aluno usando o CPF dentro da janela permitida.
5. Acompanhe as aulas liberadas semanalmente.
6. Quando uma aula paga for concluida, informe os dados do cartao para registrar o pagamento e o progresso no mesmo fluxo.

## Regras de negocio implementadas

- Login obrigatorio para uso dos servicos de negocio
- CPF unico e escolaridade no `user-service`
- Limite de 200 alunos por turma
- Janela de matricula entre 35 e 7 dias antes do inicio do curso
- Entrega final em 180 dias apos a matricula
- Persistencia do acesso por 2 semestres (360 dias)
- Grupos automaticos de ate 5 alunos
- Aulas em cards de texto, imagem, video, PDF, link ou embed
- Aulas com ordem obrigatoria
- Limite de 40 aulas por curso
- Duracao padrao: video 30 min, texto 30 min e atividade 60 min
- Apenas uma aula nova liberada por semana, baseada na data da matricula
- Pagamento por aula paga no momento da conclusao
- Consulta administrativa do progresso individual dos alunos por turma

## Observacoes

- Cada servico possui seu proprio banco PostgreSQL isolado.
- Os scripts SQL ficam em `services/*/sql/schema.sql`.
- Os servicos usam `FastAPI`, com logs basicos e tratamento de erros por `HTTPException`.
