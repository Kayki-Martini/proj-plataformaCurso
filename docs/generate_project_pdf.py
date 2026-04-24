from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "SISTEMA_EAD_DOCUMENTACAO.pdf"


BLUE = colors.HexColor("#0F4C81")
TEAL = colors.HexColor("#0B7285")
GREEN = colors.HexColor("#2F9E44")
ORANGE = colors.HexColor("#F08C00")
PURPLE = colors.HexColor("#5F3DC4")
DARK = colors.HexColor("#243447")
LIGHT = colors.HexColor("#F6F8FA")
GRID = colors.HexColor("#D9E2EC")


def build_styles():
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            name="DocTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=BLUE,
            alignment=TA_CENTER,
            spaceAfter=16,
        )
    )
    base.add(
        ParagraphStyle(
            name="Section",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=BLUE,
            spaceBefore=14,
            spaceAfter=8,
        )
    )
    base.add(
        ParagraphStyle(
            name="Subsection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=DARK,
            spaceBefore=10,
            spaceAfter=5,
        )
    )
    base.add(
        ParagraphStyle(
            name="BodyDoc",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.2,
            spaceAfter=5,
        )
    )
    base.add(
        ParagraphStyle(
            name="Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.6,
            leading=9.5,
        )
    )
    base.add(
        ParagraphStyle(
            name="CodeBlock",
            parent=base["BodyText"],
            fontName="Courier",
            fontSize=7.6,
            leading=10,
            backColor=colors.HexColor("#F3F4F6"),
            borderColor=colors.HexColor("#E5E7EB"),
            borderWidth=0.3,
            borderPadding=4,
        )
    )
    return base


styles = build_styles()


def p(text, style="BodyDoc"):
    return Paragraph(text, styles[style])


def bullet(text):
    return Paragraph(f"- {text}", styles["BodyDoc"])


def table(data, widths=None, header=True):
    converted = []
    for row_index, row in enumerate(data):
        converted_row = []
        for cell in row:
            style = "Small" if row_index else "Small"
            converted_row.append(Paragraph(str(cell), styles[style]))
        converted.append(converted_row)
    t = Table(converted, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, GRID),
                ("BACKGROUND", (0, 0), (-1, 0), BLUE if header else colors.white),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if header else colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ]
        )
    )
    return t


class BoxDiagram(Flowable):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.width = 17.2 * cm
        self.height = {
            "architecture": 8.9 * cm,
            "payment": 8.0 * cm,
            "erd": 9.2 * cm,
            "deployment": 7.7 * cm,
        }[kind]

    def wrap(self, availWidth, availHeight):
        return min(self.width, availWidth), self.height

    def draw_box(self, c, x, y, w, h, label, fill, text=colors.white):
        c.setFillColor(fill)
        c.setStrokeColor(fill)
        c.roundRect(x, y, w, h, 7, stroke=1, fill=1)
        c.setFillColor(text)
        c.setFont("Helvetica-Bold", 7.2)
        lines = label.split("\n")
        start = y + h / 2 + (len(lines) - 1) * 4
        for i, line in enumerate(lines):
            c.drawCentredString(x + w / 2, start - i * 9, line)

    def arrow(self, c, x1, y1, x2, y2, color=DARK):
        c.setStrokeColor(color)
        c.setLineWidth(1)
        c.line(x1, y1, x2, y2)
        if x2 >= x1:
            c.line(x2, y2, x2 - 5, y2 + 3)
            c.line(x2, y2, x2 - 5, y2 - 3)
        else:
            c.line(x2, y2, x2 + 5, y2 + 3)
            c.line(x2, y2, x2 + 5, y2 - 3)

    def draw(self):
        c = self.canv
        if self.kind == "architecture":
            self.draw_architecture(c)
        elif self.kind == "payment":
            self.draw_payment(c)
        elif self.kind == "erd":
            self.draw_erd(c)
        elif self.kind == "deployment":
            self.draw_deployment(c)

    def draw_architecture(self, c):
        y_top = self.height - 1.0 * cm
        self.draw_box(c, 0.4 * cm, y_top, 3.5 * cm, 1.0 * cm, "Browser\nUsuario", BLUE)
        self.draw_box(c, 4.6 * cm, y_top, 3.8 * cm, 1.0 * cm, "Frontend\nReact/Vite", TEAL)
        self.draw_box(c, 9.2 * cm, y_top, 3.0 * cm, 1.0 * cm, "Gateway\nNginx", ORANGE)
        self.arrow(c, 3.9 * cm, y_top + 0.5 * cm, 4.6 * cm, y_top + 0.5 * cm)
        self.arrow(c, 8.4 * cm, y_top + 0.5 * cm, 9.2 * cm, y_top + 0.5 * cm)

        services = [
            ("auth\n8001", 0.2, 4.7, BLUE),
            ("users\n8002", 2.6, 4.7, BLUE),
            ("courses\n8003", 5.0, 4.7, BLUE),
            ("enroll\n8004", 7.4, 4.7, BLUE),
            ("lessons\n8005", 9.8, 4.7, BLUE),
            ("progress\n8006", 12.2, 4.7, BLUE),
            ("payments\n8007", 14.6, 4.7, BLUE),
        ]
        for label, x, y, fill in services:
            self.draw_box(c, x * cm, y * cm, 2.0 * cm, 0.85 * cm, label, fill)
            self.arrow(c, 10.7 * cm, y_top, (x + 1.0) * cm, (y + 0.85) * cm, ORANGE)
            self.draw_box(c, x * cm, 2.8 * cm, 2.0 * cm, 0.65 * cm, label.split("\n")[0] + "-db", GREEN)
            self.arrow(c, (x + 1.0) * cm, y * cm, (x + 1.0) * cm, 3.45 * cm, GREEN)

        c.setFillColor(DARK)
        c.setFont("Helvetica", 7.5)
        c.drawString(0.2 * cm, 1.7 * cm, "Dependencias internas: enrollment -> users/courses; progress -> enrollments/lessons/payments/users; payments -> courses/lessons/enrollments.")

    def draw_payment(self, c):
        actors = [
            ("Aluno", 0.3),
            ("Frontend", 3.1),
            ("progress", 6.1),
            ("payment", 9.2),
            ("lessons", 12.2),
            ("enroll", 15.0),
        ]
        top = self.height - 0.8 * cm
        bottom = 0.8 * cm
        for name, x in actors:
            self.draw_box(c, x * cm, top, 2.1 * cm, 0.62 * cm, name, BLUE)
            c.setStrokeColor(GRID)
            c.line((x + 1.05) * cm, top, (x + 1.05) * cm, bottom)

        arrows = [
            (1.35, 4.15, 4.15, 4.15, "concluir aula paga"),
            (4.15, 3.55, 7.15, 3.55, "POST /progress + payment"),
            (7.15, 2.95, 10.25, 2.95, "POST /payments"),
            (10.25, 2.35, 13.25, 2.35, "valida aula/preco"),
            (10.25, 1.75, 16.05, 1.75, "valida matricula/acesso"),
            (10.25, 1.15, 7.15, 1.15, "pagamento aprovado"),
            (7.15, 0.55, 4.15, 0.55, "progresso registrado"),
        ]
        for x1, y1, x2, y2, label in arrows:
            self.arrow(c, x1 * cm, y1 * cm, x2 * cm, y2 * cm, DARK)
            c.setFillColor(DARK)
            c.setFont("Helvetica", 6.5)
            c.drawString(min(x1, x2) * cm + 0.12 * cm, y1 * cm + 0.08 * cm, label)

    def draw_erd(self, c):
        boxes = [
            ("users\nid, name, email, role", 0.3, 6.8, BLUE),
            ("students\nauth_user_id, cpf,\neducation_level", 4.1, 6.8, TEAL),
            ("courses\nstart/end, capacity,\nprice, is_paid", 8.1, 6.8, BLUE),
            ("enrollments\nuser_id, course_id,\ngroup, deadlines", 12.1, 6.8, TEAL),
            ("lessons\ncourse_id, order,\nrelease, cards", 0.3, 3.8, PURPLE),
            ("progress_entries\nuser_id, course_id,\nlesson_id", 4.1, 3.8, GREEN),
            ("payments\nuser_id, lesson_id,\namount, card meta", 8.1, 3.8, ORANGE),
        ]
        for label, x, y, fill in boxes:
            self.draw_box(c, x * cm, y * cm, 3.3 * cm, 1.45 * cm, label, fill)
        links = [
            (3.6, 7.5, 4.1, 7.5),
            (7.4, 7.5, 8.1, 7.5),
            (11.4, 7.5, 12.1, 7.5),
            (9.75, 6.8, 1.95, 5.25),
            (1.95, 3.8, 5.75, 3.8),
            (3.6, 4.45, 8.1, 4.45),
        ]
        for x1, y1, x2, y2 in links:
            self.arrow(c, x1 * cm, y1 * cm, x2 * cm, y2 * cm, DARK)
        c.setFillColor(DARK)
        c.setFont("Helvetica", 7.2)
        c.drawString(0.3 * cm, 2.3 * cm, "Relacoes sao logicas: cada microservico possui banco isolado e nao ha foreign keys entre bancos.")

    def draw_deployment(self, c):
        self.draw_box(c, 0.5 * cm, 5.7 * cm, 4.2 * cm, 0.85 * cm, "docker compose", DARK)
        self.draw_box(c, 5.5 * cm, 5.7 * cm, 4.0 * cm, 0.85 * cm, "gateway :8080", ORANGE)
        self.draw_box(c, 10.2 * cm, 5.7 * cm, 4.0 * cm, 0.85 * cm, "frontend :3000", TEAL)
        self.arrow(c, 4.7 * cm, 6.12 * cm, 5.5 * cm, 6.12 * cm)
        self.arrow(c, 9.5 * cm, 6.12 * cm, 10.2 * cm, 6.12 * cm)
        rows = [
            ("auth-service", "auth-db", 1.0, 3.8),
            ("user-service", "user-db", 5.2, 3.8),
            ("course-service", "course-db", 9.4, 3.8),
            ("enrollment-service", "enrollment-db", 13.6, 3.8),
            ("lesson-service", "lesson-db", 1.0, 2.1),
            ("progress-service", "progress-db", 5.2, 2.1),
            ("payment-service", "payment-db", 9.4, 2.1),
        ]
        for service, db, x, y in rows:
            self.draw_box(c, x * cm, y * cm, 3.2 * cm, 0.65 * cm, service, BLUE)
            self.draw_box(c, x * cm, (y - 0.8) * cm, 3.2 * cm, 0.55 * cm, db, GREEN)
            self.arrow(c, (x + 1.6) * cm, y * cm, (x + 1.6) * cm, (y - 0.25) * cm, GREEN)


def page_footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawString(1.4 * cm, 1.0 * cm, "Plataforma EAD em Microservicos - Documentacao Tecnica")
    canvas.drawRightString(A4[0] - 1.4 * cm, 1.0 * cm, f"Pagina {doc.page}")
    canvas.restoreState()


def add_service_section(story, title, responsibility, endpoints, rules, table_name):
    story.append(p(title, "Subsection"))
    story.append(p(responsibility))
    story.append(table([["Metodo", "Rota", "Descricao"], *endpoints], [2.2 * cm, 5.0 * cm, 9.2 * cm]))
    story.append(Spacer(1, 0.18 * cm))
    for item in rules:
        story.append(bullet(item))
    story.append(p(f"Tabela principal: {table_name}.", "Small"))


def build_story():
    story = []
    story.append(p("Plataforma EAD em Microservicos", "DocTitle"))
    story.append(p("Documentacao tecnica, funcional, arquitetura, modelo de dados e especificacoes. Estado do projeto em 24/04/2026.", "BodyDoc"))
    story.append(Spacer(1, 0.25 * cm))
    story.append(table([
        ["Area", "Resumo"],
        ["Objetivo", "Operar cursos EAD com matricula por CPF, aulas em cards, liberacao semanal, progresso e pagamento por aula."],
        ["Arquitetura", "Frontend React, Nginx gateway, sete microservicos FastAPI e bancos PostgreSQL isolados."],
        ["Estado", "Fluxo principal implementado; atividade ENADE e debito semanal ainda pendentes."],
    ], [4.0 * cm, 12.3 * cm]))

    story.append(p("1. Arquitetura", "Section"))
    story.append(BoxDiagram("architecture"))
    story.append(p("O frontend acessa apenas o gateway. O gateway roteia as familias de rotas para os microservicos. Cada servico possui seu banco PostgreSQL proprio, preservando isolamento operacional.", "BodyDoc"))

    story.append(p("2. Stack e implantacao", "Section"))
    story.append(BoxDiagram("deployment"))
    story.append(table([
        ["Camada", "Tecnologia"],
        ["Frontend", "React 18, Vite, Tailwind CSS"],
        ["Gateway", "Nginx 1.27 Alpine"],
        ["Backend", "FastAPI, Pydantic, SQLAlchemy"],
        ["Auth", "JWT HS256, python-jose, passlib/bcrypt"],
        ["Banco", "PostgreSQL 16, um banco por servico"],
        ["Orquestracao", "Docker Compose"],
    ], [4.2 * cm, 12.0 * cm]))

    story.append(PageBreak())
    story.append(p("3. Servicos e contratos", "Section"))
    add_service_section(
        story,
        "auth-service",
        "Registro, login, JWT e roles.",
        [
            ["GET", "/health", "Saude do servico"],
            ["POST", "/auth/register", "Cria usuario aluno ou admin"],
            ["POST", "/auth/login", "Autentica e retorna JWT"],
            ["GET", "/auth/me", "Retorna usuario autenticado"],
        ],
        ["Roles permitidas: admin e aluno.", "Admin exige ADMIN_REGISTRATION_CODE.", "JWT contem sub, name, email, role e exp."],
        "users",
    )
    add_service_section(
        story,
        "user-service",
        "Perfil do aluno por CPF.",
        [
            ["GET", "/health", "Saude do servico"],
            ["GET", "/users", "Lista alunos; filtros cpf e auth_user_id"],
            ["POST", "/users", "Cria perfil"],
            ["PUT", "/users/{user_id}", "Atualiza perfil"],
            ["DELETE", "/users/{user_id}", "Remove perfil"],
        ],
        ["CPF unico.", "Usuario comum so acessa o proprio perfil.", "Campos incluem WhatsApp, Telegram, cidade, estado e escolaridade."],
        "students",
    )
    add_service_section(
        story,
        "course-service",
        "Catalogo, turmas e janela de matricula.",
        [
            ["GET", "/health", "Saude do servico"],
            ["GET", "/courses", "Lista cursos"],
            ["GET", "/courses/{course_id}", "Detalha curso"],
            ["POST", "/courses", "Cria curso; admin"],
            ["PUT", "/courses/{course_id}", "Atualiza curso; admin"],
        ],
        ["Capacidade maxima de 200 alunos.", "Janela calculada: 5 a 1 semanas antes do inicio.", "Curso pago deriva de price > 0 quando nao informado."],
        "courses",
    )

    story.append(PageBreak())
    add_service_section(
        story,
        "enrollment-service",
        "Matricula por CPF.",
        [
            ["GET", "/health", "Saude do servico"],
            ["POST", "/enrollments", "Cria matricula"],
            ["GET", "/enrollments/user/{user_id}", "Lista matriculas do usuario"],
            ["GET", "/enrollments/course/{course_id}", "Lista matriculas da turma; admin"],
        ],
        ["Busca aluno por CPF.", "Matricula permitida apenas na janela operacional.", "Grupos automaticos de ate 5 alunos.", "Final delivery em 180 dias e acesso em 360 dias."],
        "enrollments",
    )
    add_service_section(
        story,
        "lesson-service",
        "Curriculo, aulas e cards multimidia.",
        [
            ["GET", "/health", "Saude do servico"],
            ["GET", "/lessons/course/{course_id}", "Lista aulas do curso"],
            ["GET", "/lessons/{lesson_id}", "Detalha aula"],
            ["POST", "/lessons", "Cria aula; admin"],
        ],
        ["Maximo de 40 aulas por curso.", "Video e texto duram 30 min; atividade dura 60 min.", "Cards: texto, imagem, video, PDF, link e embed.", "release_week segue order_index."],
        "lessons",
    )
    add_service_section(
        story,
        "progress-service",
        "Progresso, sequencia e leitura administrativa da turma.",
        [
            ["GET", "/health", "Saude do servico"],
            ["POST", "/progress", "Marca aula concluida"],
            ["GET", "/progress/{user_id}", "Progresso por curso"],
            ["GET", "/progress/course/{course_id}/students", "Progresso por aluno; admin"],
        ],
        ["Valida matricula, acesso, liberacao semanal e ordem.", "Em aula paga chama payment-service antes de registrar progresso.", "Admin enxerga percentual, proxima aula e dados do aluno."],
        "progress_entries",
    )
    add_service_section(
        story,
        "payment-service",
        "Pagamento por aula no cartao.",
        [
            ["GET", "/health", "Saude do servico"],
            ["POST", "/payments", "Registra pagamento de aula"],
            ["GET", "/payments/{user_id}", "Lista pagamentos do usuario"],
        ],
        ["Nao persiste numero completo do cartao nem CVV.", "Impede duplicidade por usuario/aula paga.", "Valor precisa ser exatamente igual ao preco da aula.", "Valida matricula, liberacao e acesso."],
        "payments",
    )

    story.append(PageBreak())
    story.append(p("4. Modelo de dados", "Section"))
    story.append(BoxDiagram("erd"))
    story.append(table([
        ["Tabela", "Campos principais"],
        ["users", "id, name, email, hashed_password, role, created_at"],
        ["students", "auth_user_id, cpf, name, email, whatsapp, telegram, city, state, education_level"],
        ["courses", "title, description, cohort_name, start_date, end_date, capacity, price, is_paid, is_active"],
        ["enrollments", "user_id, student_id, course_id, cpf, group_number, deadlines"],
        ["lessons", "course_id, title, type, order_index, release_week, duration_minutes, price, cards_json"],
        ["progress_entries", "user_id, course_id, lesson_id, completed_at"],
        ["payments", "user_id, course_id, lesson_id, amount, status, provider, card_brand, card_last_four"],
    ], [4.0 * cm, 12.4 * cm]))

    story.append(p("5. Fluxo de pagamento e progresso", "Section"))
    story.append(BoxDiagram("payment"))
    story.append(p("A conclusao de aula paga nasce no frontend, passa pelo progress-service, aciona o payment-service quando necessario e so entao grava o progresso. Essa ordem evita concluir uma aula paga sem pagamento aprovado.", "BodyDoc"))

    story.append(PageBreak())
    story.append(p("6. Regras de negocio", "Section"))
    story.append(table([
        ["Regra", "Status"],
        ["Login obrigatorio para operacoes de negocio", "Implementado"],
        ["Roles admin e aluno", "Implementado"],
        ["Perfil por CPF e CPF unico", "Implementado"],
        ["Escolaridade no cadastro do aluno", "Implementado"],
        ["Capacidade maxima de 200 alunos", "Implementado"],
        ["Grupos automaticos de ate 5 alunos", "Implementado"],
        ["Matricula entre 5 e 1 semanas antes do curso", "Implementado"],
        ["Entrega final em 180 dias", "Implementado"],
        ["Acesso por 360 dias", "Implementado"],
        ["Curso com ate 40 aulas", "Implementado"],
        ["Video 30 min, texto 30 min, atividade 60 min", "Implementado"],
        ["Liberacao semanal e ordem sequencial", "Implementado"],
        ["Cards multimidia", "Implementado"],
        ["Pagamento por aula paga na conclusao", "Implementado"],
        ["Progresso individual por aluno/turma", "Implementado"],
        ["Atividade ENADE com 30 questoes objetivas", "Pendente"],
        ["Debito financeiro no final da semana", "Pendente"],
        ["Normalizacao cidade/estado em tabelas proprias", "Pendente"],
    ], [11.8 * cm, 4.4 * cm]))

    story.append(p("7. Frontend", "Section"))
    story.append(table([
        ["Rota", "Descricao"],
        ["/login", "Login e registro"],
        ["/dashboard", "Perfil, matriculas e resumo"],
        ["/courses", "Catalogo e matricula"],
        ["/lessons", "Cards, liberacao, conclusao e pagamento"],
        ["/admin", "Studio Admin para cursos e aulas"],
        ["/progress", "Progresso do aluno ou turma para admin"],
    ], [4.0 * cm, 12.0 * cm]))
    for item in [
        "Usa VITE_API_URL com default http://localhost:8080.",
        "Armazena JWT em localStorage como ead-token.",
        "Exige CPF antes da matricula.",
        "Abre modal de cartao somente na conclusao de aula paga.",
        "Admin cria cursos e aulas no Studio Admin.",
    ]:
        story.append(bullet(item))

    story.append(p("8. Execucao e validacao", "Section"))
    story.append(p("Comando principal:", "BodyDoc"))
    story.append(p("docker compose up -d --build", "CodeBlock"))
    story.append(p("Acessos: frontend http://localhost:3000, gateway http://localhost:8080/health, Swagger dos servicos nas portas 8001 a 8007.", "BodyDoc"))
    story.append(p("Validacoes realizadas: py_compile dos main.py, import de user-service e lesson-service, build do frontend e docker compose config --quiet.", "BodyDoc"))

    story.append(p("9. Proximos passos recomendados", "Section"))
    for item in [
        "Criar modulo de atividade/prova ENADE com 30 questoes objetivas.",
        "Especificar e implementar debito no final da semana.",
        "Normalizar cidades e estados se esse requisito for obrigatorio.",
        "Adicionar testes automatizados para matricula, liberacao semanal, pagamento e progresso.",
        "Substituir migracoes em startup por migrations versionadas.",
    ]:
        story.append(bullet(item))

    return story


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.5 * cm,
        title="Plataforma EAD em Microservicos - Documentacao",
        author="Codex",
    )
    doc.build(build_story(), onFirstPage=page_footer, onLaterPages=page_footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
