# Plataforma EAD em Microserviços

Sistema completo para gestão de cursos online (EAD), com arquitetura de microserviços, API Gateway, bancos isolados por serviço, frontend React + Vite + Tailwind e orquestração com Docker Compose.

## Serviços

- `auth-service`: login, registro, JWT e roles (`admin`, `aluno`)
- `user-service`: perfil dos alunos com CPF único
- `course-service`: catálogo e turmas com capacidade máxima de 200 alunos
- `enrollment-service`: matrículas por CPF, grupos de até 5 alunos e janela entre 5 semanas e 1 semana antes do início
- `lesson-service`: aulas em cards, com ordem obrigatória, preço por aula e liberação semanal
- `progress-service`: conclusão sequencial das aulas, percentual de progresso e leitura da turma por aluno
- `payment-service`: pagamentos por aula via cartão de crédito
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

1. Registre um usuário no frontend.
2. Complete o perfil do aluno no dashboard.
3. Crie cursos e aulas no Studio Admin com um usuário `admin`.
4. Matricule o aluno usando o CPF dentro da janela permitida.
5. Acompanhe as aulas liberadas semanalmente.
6. Quando uma aula paga for concluída, informe os dados do cartão para registrar o pagamento e o progresso no mesmo fluxo.

## Regras de negócio implementadas

- Login obrigatório para uso dos serviços de negócio
- CPF único e escolaridade no `user-service`
- Limite de 200 alunos por turma
- Janela de matrícula entre 35 e 7 dias antes do início do curso
- Entrega final em 180 dias após a matrícula
- Persistência do acesso por 2 semestres (360 dias)
- Grupos automáticos de até 5 alunos
- Aulas em cards de texto, imagem, vídeo, PDF, link ou embed
- Aulas com ordem obrigatória
- Limite de 40 aulas por curso
- Duração padrão: vídeo 30 min, texto 30 min e atividade 60 min
- Apenas uma aula nova liberada por semana, baseada na data da matrícula
- Pagamento por aula paga no momento da conclusão
- Consulta administrativa do progresso individual dos alunos por turma

## Observações

- Cada serviço possui seu próprio banco PostgreSQL isolado.
- Os scripts SQL ficam em `services/*/sql/schema.sql`.
- Modelo de dados consolidado em `docs/MODELO_DE_DADOS.md`.
- Documentação técnica consolidada em `docs/SISTEMA_EAD_DOCUMENTACAO.md`.
- Prints das telas do frontend em `docs/FRONTEND_PRINTS.md`.
- Os serviços usam `FastAPI`, com logs básicos e tratamento de erros por `HTTPException`.
