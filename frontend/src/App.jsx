import { startTransition, useEffect, useState } from "react"
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom"

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8080"
const TOKEN_KEY = "ead-token"

const LESSON_CARD_TYPES = [
  {
    value: "texto",
    label: "Texto",
    hint: "Bloco rico para instrucoes, resumo da aula ou atividade guiada.",
  },
  {
    value: "imagem",
    label: "Imagem",
    hint: "Cole a URL de uma imagem publica para montar galerias, infograficos ou capas.",
  },
  {
    value: "video",
    label: "Video",
    hint: "Aceita link direto de arquivo ou URL de YouTube/Vimeo para embed.",
  },
  {
    value: "pdf",
    label: "PDF",
    hint: "Use um PDF publico para preview rapido e botao de abertura do material.",
  },
  {
    value: "link",
    label: "Link",
    hint: "Encaminhe o aluno para ferramentas externas, formularios ou referencias.",
  },
  {
    value: "embed",
    label: "Embed",
    hint: "Ideal para dashboards, lousas, mapas mentais e outros iframes publicos.",
  },
]

const CARD_TYPE_LABELS = Object.fromEntries(LESSON_CARD_TYPES.map((option) => [option.value, option.label]))

function createEmptyLessonCard(index = 1) {
  return {
    title: `Card ${index}`,
    body: "",
    asset_type: "texto",
    asset_url: "",
    button_label: "",
  }
}

function getDefaultRoute(user) {
  return user?.role === "admin" ? "/admin" : "/dashboard"
}

function getCardTypeHint(assetType) {
  return LESSON_CARD_TYPES.find((option) => option.value === assetType)?.hint ?? "Configure o card para publicar o conteudo."
}

function toEmbeddableUrl(url) {
  if (!url) return ""

  try {
    const parsed = new URL(url)
    const hostname = parsed.hostname.replace(/^www\./, "")

    if (hostname === "youtu.be") {
      const videoId = parsed.pathname.replace("/", "")
      return videoId ? `https://www.youtube.com/embed/${videoId}` : url
    }

    if (hostname === "youtube.com" || hostname === "m.youtube.com") {
      if (parsed.pathname.startsWith("/embed/")) {
        return url
      }
      const videoId = parsed.searchParams.get("v")
      return videoId ? `https://www.youtube.com/embed/${videoId}` : url
    }

    if (hostname === "vimeo.com") {
      const videoId = parsed.pathname.split("/").filter(Boolean)[0]
      return videoId ? `https://player.vimeo.com/video/${videoId}` : url
    }
  } catch {
    return url
  }

  return url
}

function isDirectVideo(url) {
  return /\.(mp4|webm|ogg|mov)(\?.*)?$/i.test(url ?? "")
}

function normalizeErrorDetail(detail) {
  if (!detail) {
    return "Nao foi possivel concluir a solicitacao."
  }

  if (typeof detail === "string") {
    return detail
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") {
          return item
        }

        if (item?.msg && Array.isArray(item.loc)) {
          const field = item.loc.filter((part) => part !== "body").join(" > ")
          return field ? `${field}: ${item.msg}` : item.msg
        }

        if (item?.msg) {
          return item.msg
        }

        return null
      })
      .filter(Boolean)

    return messages.length > 0 ? messages.join(" | ") : "Erro de validacao na requisicao."
  }

  if (typeof detail === "object") {
    if (typeof detail.message === "string") {
      return detail.message
    }

    if (typeof detail.detail === "string") {
      return detail.detail
    }
  }

  return String(detail)
}

async function apiFetch(path, { token, method = "GET", body } = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (error) {
    const message =
      error instanceof TypeError
        ? "Falha de comunicacao com a API. Verifique se o gateway e os servicos estao ativos."
        : "Nao foi possivel concluir a solicitacao."
    throw new Error(message)
  }

  if (!response.ok) {
    let detail = "Nao foi possivel concluir a solicitacao."
    try {
      const payload = await response.json()
      detail = normalizeErrorDetail(payload.detail ?? payload.message ?? detail)
    } catch {
      detail = response.statusText || detail
    }
    const error = new Error(detail)
    error.status = response.status
    throw error
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}

function formatDate(value) {
  if (!value) return "-"
  return new Date(value).toLocaleDateString("pt-BR")
}

function formatCurrency(value) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value ?? 0))
}

function normalizeDigits(value) {
  return String(value ?? "").replace(/\D/g, "")
}

function detectCardBrand(cardNumber) {
  const digits = normalizeDigits(cardNumber)
  if (digits.startsWith("4")) return "Visa"
  if (/^5[1-5]/.test(digits) || /^2(2[2-9]|[3-6]\d|7[01])/.test(digits)) return "Mastercard"
  if (/^3[47]/.test(digits)) return "Amex"
  if (/^6(?:011|5)/.test(digits)) return "Discover"
  if (/^35/.test(digits)) return "JCB"
  return "Cartao de credito"
}

function sumPaidAmount(payments) {
  return payments
    .filter((item) => item.status === "paid")
    .reduce((acc, item) => acc + Number(item.amount ?? 0), 0)
}

function DashboardPage({
  currentUser,
  courses,
  profile,
  enrollments,
  progress,
  payments,
  notice,
  onNotice,
  onSaveProfile,
}) {
  const [form, setForm] = useState({
    cpf: "",
    name: currentUser?.name ?? "",
    email: currentUser?.email ?? "",
    whatsapp: "",
    telegram: "",
    city: "",
    state: "",
    education_level: "medio",
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setForm({
      cpf: profile?.cpf ?? "",
      name: profile?.name ?? currentUser?.name ?? "",
      email: profile?.email ?? currentUser?.email ?? "",
      whatsapp: profile?.whatsapp ?? "",
      telegram: profile?.telegram ?? "",
      city: profile?.city ?? "",
      state: profile?.state ?? "",
      education_level: profile?.education_level ?? "medio",
    })
  }, [profile, currentUser])

  const averageProgress =
    progress.length > 0
      ? Math.round(progress.reduce((acc, item) => acc + item.percentage, 0) / progress.length)
      : 0
  const paidLessons = payments.filter((item) => item.status === "paid").length
  const totalSpent = sumPaidAmount(payments)

  if (currentUser?.role === "admin") {
    return (
      <div className="page-enter space-y-8">
        <section className="grid gap-5 lg:grid-cols-[1.35fr,0.65fr]">
          <div className="glass-panel overflow-hidden p-8">
            <div className="mb-6 inline-flex rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.35em] text-surf">
              visao admin
            </div>
            <h1 className="max-w-3xl font-serif text-4xl text-white sm:text-5xl">
              Seu cockpit administrativo agora separa cadastro, curriculo e experiencia do aluno.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-300">
              Use o Studio Admin para cadastrar cursos e desenhar aulas em cards. O restante da plataforma fica livre para catalogo, progresso e consumo do conteudo final.
            </p>
            <NavLink className="soft-button-primary mt-6 w-full sm:w-auto" to="/admin">
              Abrir Studio Admin
            </NavLink>
          </div>

          <div className="grid gap-4">
            <StatCard label="Cursos publicados" value={courses.length} accent="from-surf to-cyan-400" />
            <StatCard label="Pagamentos do seu usuario" value={paidLessons} accent="from-mango to-coral" />
            <StatCard label="Acesso administrativo" value="ativo" accent="from-emerald-400 to-lime-300" />
          </div>
        </section>

        <section className="glass-panel p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold text-white">Cursos mais recentes</h2>
              <p className="mt-1 text-sm text-slate-300">Confira rapidamente as turmas ja disponiveis antes de editar aulas no Studio Admin.</p>
            </div>
            <NavLink className="soft-button-muted" to="/courses">
              Ver catalogo
            </NavLink>
          </div>
          <div className="mt-5 grid gap-4 xl:grid-cols-2">
            {courses.length === 0 ? (
              <EmptyState title="Nenhum curso publicado" text="Crie o primeiro curso para liberar a aba de aulas no Studio Admin." />
            ) : (
              [...courses]
                .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                .slice(0, 4)
                .map((course) => (
                  <article key={course.id} className="rounded-3xl border border-white/10 bg-slate-950/35 p-5">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-lg font-semibold text-white">{course.title}</h3>
                      <span className="rounded-full bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.25em] text-slate-300">
                        {course.cohort_name}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-300">{course.description}</p>
                    <dl className="mt-4 space-y-2 text-sm text-slate-200">
                      <InfoRow label="Inicio" value={formatDate(course.start_date)} />
                      <InfoRow label="Janela" value={`${formatDate(course.enrollment_window_open)} ate ${formatDate(course.enrollment_window_close)}`} />
                    </dl>
                  </article>
                ))
            )}
          </div>
        </section>
      </div>
    )
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setSaving(true)
    try {
      await onSaveProfile(form)
      onNotice({ type: "success", text: "Perfil salvo com sucesso." })
    } catch (error) {
      onNotice({ type: "error", text: error.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page-enter space-y-8">
      <section className="grid gap-5 lg:grid-cols-[1.5fr,1fr]">
        <div className="glass-panel overflow-hidden p-8">
          <div className="mb-6 inline-flex rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.35em] text-surf">
            painel principal
          </div>
          <h1 className="max-w-2xl font-serif text-4xl text-white sm:text-5xl">
            {currentUser?.name}, sua operacao EAD esta concentrada em um unico cockpit.
          </h1>
          <p className="mt-4 max-w-2xl text-sm text-slate-300">
            Complete o perfil, acompanhe matriculas, veja a vigencia do acesso e monitore o ritmo de estudos de cada curso.
          </p>
          {notice ? (
            <div
              className={`mt-6 rounded-2xl border px-4 py-3 text-sm ${
                notice.type === "success"
                  ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100"
                  : "border-coral/40 bg-coral/10 text-rose-100"
              }`}
            >
              {notice.text}
            </div>
          ) : null}
        </div>

        <div className="grid gap-4">
          <StatCard label="Cursos ativos" value={enrollments.length} accent="from-surf to-cyan-400" />
          <StatCard label="Media de progresso" value={`${averageProgress}%`} accent="from-mango to-coral" />
          <StatCard label="Aulas pagas" value={paidLessons} accent="from-emerald-400 to-lime-300" />
          <StatCard
            label="Total investido"
            value={formatCurrency(totalSpent)}
            accent="from-fuchsia-400 to-sky-400"
          />
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.2fr,0.8fr]">
        <form className="glass-panel p-6" onSubmit={handleSubmit}>
          <div className="mb-5">
            <h2 className="text-2xl font-semibold text-white">Perfil do aluno</h2>
            <p className="mt-1 text-sm text-slate-300">
              O CPF e obrigatorio para matricula. Os demais dados alimentam o relacionamento e a comunicacao.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <FieldInput label="CPF" value={form.cpf} onChange={(value) => setForm((prev) => ({ ...prev, cpf: value }))} />
            <FieldInput label="Nome" value={form.name} onChange={(value) => setForm((prev) => ({ ...prev, name: value }))} />
            <FieldInput label="Email" value={form.email} onChange={(value) => setForm((prev) => ({ ...prev, email: value }))} />
            <FieldInput
              label="WhatsApp"
              value={form.whatsapp}
              onChange={(value) => setForm((prev) => ({ ...prev, whatsapp: value }))}
            />
            <FieldInput
              label="Telegram"
              value={form.telegram}
              onChange={(value) => setForm((prev) => ({ ...prev, telegram: value }))}
            />
            <FieldInput label="Cidade" value={form.city} onChange={(value) => setForm((prev) => ({ ...prev, city: value }))} />
            <FieldInput label="Estado" value={form.state} onChange={(value) => setForm((prev) => ({ ...prev, state: value }))} />
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-200">Escolaridade</label>
              <select
                className="soft-input"
                onChange={(event) => setForm((prev) => ({ ...prev, education_level: event.target.value }))}
                value={form.education_level}
              >
                <option value="medio">Ensino medio</option>
                <option value="superior">Ensino superior</option>
                <option value="pos-graduacao">Pos-graduacao</option>
              </select>
            </div>
          </div>
          <button className="soft-button-primary mt-6 w-full" disabled={saving} type="submit">
            {saving ? "Salvando..." : profile?.id ? "Atualizar perfil" : "Criar perfil"}
          </button>
        </form>

        <div className="glass-panel p-6">
          <h2 className="text-2xl font-semibold text-white">Seus cursos</h2>
          <div className="mt-5 space-y-4">
            {enrollments.length === 0 ? (
              <EmptyState
                title="Nenhuma matricula ainda"
                text="Assim que voce se matricular em um curso, ele aparece aqui com prazo final e grupo."
              />
            ) : (
              enrollments.map((enrollment) => {
                const courseProgress = progress.find((item) => item.course_id === enrollment.course_id)
                return (
                  <article key={enrollment.id} className="rounded-3xl border border-white/10 bg-slate-900/60 p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <h3 className="text-lg font-semibold text-white">{enrollment.course_title}</h3>
                        <p className="text-sm text-slate-300">
                          Grupo {enrollment.group_number} - prazo final {formatDate(enrollment.final_delivery_deadline)}
                        </p>
                      </div>
                      <span className="rounded-full bg-surf/[0.15] px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-surf">
                        {courseProgress?.percentage ?? 0}%
                      </span>
                    </div>
                  </article>
                )
              })
            )}
          </div>
        </div>
      </section>
    </div>
  )
}

function CoursesPage({
  currentUser,
  profile,
  courses,
  enrollments,
  onEnroll,
  notice,
}) {
  const activeCourses = courses.filter((course) => course.is_active)
  const paidCourses = courses.filter((course) => course.is_paid)

  return (
    <div className="page-enter space-y-6">
      <section className="grid gap-5 lg:grid-cols-[1.4fr,0.8fr]">
        <div className="glass-panel overflow-hidden p-8">
          <div className="mb-6 inline-flex rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.35em] text-surf">
            catalogo
          </div>
          <h1 className="max-w-3xl font-serif text-4xl text-white sm:text-5xl">
            Cursos organizados por turma, janela de matricula e valor.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-300">
            Aqui fica a vitrine da operacao EAD. Cursos pagos agora cobram no cartao aula por aula, conforme o aluno conclui a trilha.
          </p>
          {currentUser?.role === "admin" ? (
            <div className="mt-6 rounded-3xl border border-surf/25 bg-surf/[0.08] p-5">
              <p className="text-sm leading-6 text-slate-200">
                O fluxo administrativo foi separado do catalogo publico. Use o Studio Admin para cadastrar cursos, escolher a turma e desenhar as aulas em cards de PDF, video, imagem, link ou embed.
              </p>
              <NavLink className="soft-button-primary mt-4 w-full sm:w-auto" to="/admin">
                Abrir Studio Admin
              </NavLink>
            </div>
          ) : null}
        </div>

        <div className="grid gap-4">
          <StatCard label="Cursos ativos" value={activeCourses.length} accent="from-surf to-cyan-400" />
          <StatCard label="Cursos pagos" value={paidCourses.length} accent="from-mango to-coral" />
          <StatCard label="Suas matriculas" value={enrollments.length} accent="from-emerald-400 to-lime-300" />
        </div>
      </section>

      {notice ? (
        <div
          className={`rounded-2xl border px-4 py-3 text-sm ${
            notice.type === "success"
              ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100"
              : "border-coral/40 bg-coral/10 text-rose-100"
          }`}
        >
          {notice.text}
        </div>
      ) : null}

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {courses.map((course) => {
          const enrollment = enrollments.find((item) => item.course_id === course.id)
          return (
            <article key={course.id} className="glass-panel flex flex-col p-6">
              <div className="mb-4 flex items-center justify-between gap-3">
                <span className="rounded-full bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.28em] text-slate-200">
                  {course.category || "trilha"}
                </span>
                <span className="rounded-full bg-mango/[0.15] px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-mango">
                  {course.is_paid ? `${formatCurrency(course.price)} por aula` : "gratuito"}
                </span>
              </div>
              <h2 className="text-2xl font-semibold text-white">{course.title}</h2>
              <p className="mt-3 flex-1 text-sm leading-6 text-slate-300">{course.description}</p>
              <dl className="mt-5 space-y-2 text-sm text-slate-200">
                <InfoRow label="Turma" value={course.cohort_name} />
                <InfoRow label="Inicio" value={formatDate(course.start_date)} />
                <InfoRow label="Janela" value={`${formatDate(course.enrollment_window_open)} ate ${formatDate(course.enrollment_window_close)}`} />
                <InfoRow label="Capacidade" value={`${course.capacity} alunos`} />
              </dl>
              {enrollment ? (
                <button className="soft-button-muted mt-6 w-full" disabled type="button">
                  Matriculado no grupo {enrollment.group_number}
                </button>
              ) : currentUser?.role === "admin" ? (
                <button className="soft-button-muted mt-6 w-full" disabled type="button">
                  Matriculas de admin sao feitas via conta de aluno
                </button>
              ) : (
                <button
                  className="soft-button-primary mt-6 w-full"
                  onClick={() => onEnroll(course)}
                  type="button"
                >
                  Matricular agora
                </button>
              )}
              {course.is_paid ? (
                <p className="mt-3 text-xs leading-5 text-slate-300">O cartao de credito sera cobrado apenas nas aulas pagas que voce concluir.</p>
              ) : null}
              {!profile?.cpf && currentUser?.role !== "admin" ? (
                <p className="mt-3 text-xs text-coral">Complete seu perfil com CPF no dashboard antes de se matricular.</p>
              ) : null}
            </article>
          )
        })}
      </section>
    </div>
  )
}

function LessonsPage({
  currentUser,
  courses,
  enrollments,
  progress,
  lessons,
  payments,
  selectedCourseId,
  onSelectCourse,
  onCompleteLesson,
  onNotice,
  notice,
}) {
  const visibleCourses =
    currentUser?.role === "admin"
      ? courses
      : courses.filter((course) => enrollments.some((item) => item.course_id === course.id))
  const selectedCourse = visibleCourses.find((course) => String(course.id) === String(selectedCourseId))
  const activeProgress = progress.find((item) => item.course_id === Number(selectedCourseId))
  const completedCount = activeProgress?.completed_lessons ?? 0
  const availableLessons = activeProgress?.available_lessons ?? 0
  const [paymentModalLesson, setPaymentModalLesson] = useState(null)
  const [processingLessonId, setProcessingLessonId] = useState(null)
  const [paymentForm, setPaymentForm] = useState({
    card_holder_name: currentUser?.name ?? "",
    card_number: "",
    expiry_month: "",
    expiry_year: "",
    cvv: "",
  })

  useEffect(() => {
    setPaymentModalLesson(null)
    setPaymentForm({
      card_holder_name: currentUser?.name ?? "",
      card_number: "",
      expiry_month: "",
      expiry_year: "",
      cvv: "",
    })
  }, [currentUser?.name, selectedCourseId])

  const paymentBrand = detectCardBrand(paymentForm.card_number)

  function openPaymentModal(lesson) {
    setPaymentModalLesson(lesson)
    setPaymentForm({
      card_holder_name: currentUser?.name ?? "",
      card_number: "",
      expiry_month: "",
      expiry_year: "",
      cvv: "",
    })
  }

  function closePaymentModal() {
    setPaymentModalLesson(null)
  }

  async function submitLessonCompletion(lesson, paymentPayload) {
    setProcessingLessonId(lesson.id)
    try {
      await onCompleteLesson(Number(selectedCourseId), lesson.id, paymentPayload ? { payment: paymentPayload } : undefined)
      if (paymentPayload) {
        closePaymentModal()
      }
    } catch (error) {
      onNotice({ type: "error", text: error.message })
    } finally {
      setProcessingLessonId(null)
    }
  }

  async function handleLessonAction(lesson, paymentRecord) {
    if (Number(lesson.price ?? 0) > 0 && !paymentRecord) {
      openPaymentModal(lesson)
      return
    }

    await submitLessonCompletion(lesson)
  }

  async function handlePaymentSubmit(event) {
    event.preventDefault()
    if (!paymentModalLesson) return

    await submitLessonCompletion(paymentModalLesson, {
      card_holder_name: paymentForm.card_holder_name.trim(),
      card_number: paymentForm.card_number.trim(),
      expiry_month: Number(paymentForm.expiry_month),
      expiry_year: Number(paymentForm.expiry_year),
      cvv: paymentForm.cvv.trim(),
    })
  }

  return (
    <div className="page-enter space-y-6">
      <section className="grid gap-5 lg:grid-cols-[1.25fr,0.75fr]">
        <div className="glass-panel p-8">
          <div className="mb-6 inline-flex rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.35em] text-surf">
            jornada
          </div>
          <h1 className="max-w-3xl font-serif text-4xl text-white sm:text-5xl">
            Aulas em cards com liberacao semanal e ordem protegida.
          </h1>
          <p className="mt-4 max-w-2xl text-sm leading-7 text-slate-300">
            Cada aula pode combinar texto, imagem, video, PDF, links externos ou embeds. Quando a trilha for paga, a cobranca acontece no cartao aula por aula, no momento da conclusao.
          </p>
          {currentUser?.role === "admin" ? (
            <div className="mt-6 rounded-3xl border border-mango/30 bg-mango/[0.08] p-5">
              <p className="text-sm leading-6 text-slate-200">
                A criacao de cursos e aulas agora acontece no Studio Admin. Esta tela ficou focada na visualizacao da experiencia final e no acompanhamento da liberacao dos cards.
              </p>
              <NavLink className="soft-button-primary mt-4 w-full sm:w-auto" to="/admin">
                Montar aulas no Studio Admin
              </NavLink>
            </div>
          ) : null}
        </div>

        <div className="glass-panel space-y-5 p-6">
          <div>
            <h2 className="text-xl font-semibold text-white">Curso em foco</h2>
            <p className="mt-1 text-sm text-slate-300">
              Escolha a trilha para ver a sequencia, os cards liberados e o proximo passo do aluno.
            </p>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-200">Curso</label>
            <select
              className="soft-input"
              onChange={(event) => onSelectCourse(event.target.value)}
              value={selectedCourseId ?? ""}
            >
              <option value="">Selecione um curso</option>
              {visibleCourses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.title}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <MiniPill
              title="Aulas liberadas"
              text={selectedCourseId ? `${availableLessons} disponiveis para esta trilha.` : "Selecione um curso para calcular a janela."}
            />
            <MiniPill
              title="Concluidas"
              text={selectedCourseId ? `${completedCount} registradas no progresso atual.` : "O progresso aparece assim que o curso for escolhido."}
            />
          </div>
        </div>
      </section>

      {notice ? (
        <div
          className={`rounded-2xl border px-4 py-3 text-sm ${
            notice.type === "success"
              ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100"
              : "border-coral/40 bg-coral/10 text-rose-100"
          }`}
        >
          {notice.text}
        </div>
      ) : null}

      {!selectedCourseId ? <EmptyState title="Selecione um curso" text="Escolha uma trilha para abrir a grade de aulas e visualizar seus cards." /> : null}

      {selectedCourseId && lessons.length === 0 ? (
        <EmptyState title="Nenhuma aula cadastrada" text="Esse curso ainda nao recebeu aulas. Assim que o admin publicar, os cards aparecem aqui." />
      ) : null}

      {selectedCourse ? (
        <div className="glass-panel flex flex-col gap-5 p-6 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-slate-400">curriculo</p>
            <h2 className="mt-2 text-2xl font-semibold text-white">{selectedCourse.title}</h2>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-300">{selectedCourse.description}</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:w-[420px]">
            <MiniPill title="Turma" text={selectedCourse.cohort_name} />
            <MiniPill title="Cards publicados" text={`${lessons.reduce((acc, lesson) => acc + (lesson.cards?.length ?? 0), 0)} blocos nesta trilha.`} />
          </div>
        </div>
      ) : null}

      <div className="grid gap-5">
        {lessons.map((lesson) => {
          const completed = completedCount >= lesson.order_index
          const unlocked =
            currentUser?.role === "admin" || (availableLessons >= lesson.release_week && lesson.order_index <= completedCount + 1)
          const canComplete = currentUser?.role !== "admin" && unlocked && !completed
          const lessonPrice = Number(lesson.price ?? 0)
          const paymentRecord = payments.find((item) => item.lesson_id === lesson.id && item.status === "paid")
          const isProcessing = processingLessonId === lesson.id

          return (
            <article key={lesson.id} className="glass-panel overflow-hidden p-6">
              <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                <div>
                  <div className="mb-3 flex flex-wrap items-center gap-3">
                    <span className="rounded-full bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.25em] text-slate-200">
                      semana {lesson.release_week}
                    </span>
                    <span className="rounded-full bg-surf/[0.15] px-3 py-1 text-xs uppercase tracking-[0.25em] text-surf">
                      {lesson.type} - {lesson.duration_minutes} min
                    </span>
                    <span className="rounded-full bg-mango/[0.15] px-3 py-1 text-xs uppercase tracking-[0.25em] text-mango">
                      {lessonPrice > 0 ? `${formatCurrency(lessonPrice)} no cartao` : "sem cobranca"}
                    </span>
                    <span className="rounded-full bg-white/[0.06] px-3 py-1 text-xs uppercase tracking-[0.25em] text-slate-300">
                      {lesson.cards?.length ?? 0} cards
                    </span>
                  </div>
                  <h2 className="text-2xl font-semibold text-white">
                    {lesson.order_index}. {lesson.title}
                  </h2>
                  <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-300">{lesson.description}</p>
                </div>
                <div className="flex min-w-[220px] flex-col items-start gap-3 xl:items-end">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] ${
                      completed
                        ? "bg-emerald-500/[0.15] text-emerald-100"
                        : unlocked
                          ? "bg-mango/[0.15] text-mango"
                          : "bg-white/[0.08] text-slate-300"
                    }`}
                  >
                    {completed ? "concluida" : unlocked ? "disponivel" : "bloqueada"}
                  </span>
                  {paymentRecord ? (
                    <span className="rounded-full bg-emerald-500/[0.15] px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] text-emerald-100">
                      pago no {paymentRecord.card_brand || "cartao"} final {paymentRecord.card_last_four || "****"}
                    </span>
                  ) : null}
                  {canComplete ? (
                    <button className="soft-button-primary" disabled={isProcessing} onClick={() => handleLessonAction(lesson, paymentRecord)} type="button">
                      {isProcessing
                        ? "Processando..."
                        : lessonPrice > 0 && !paymentRecord
                          ? `Pagar ${formatCurrency(lessonPrice)} e concluir`
                          : "Marcar como concluida"}
                    </button>
                  ) : null}
                  {lessonPrice > 0 && !completed ? (
                    <p className="text-right text-xs leading-5 text-slate-300">
                      {paymentRecord
                        ? "Pagamento desta aula ja aprovado. Agora basta concluir o conteudo."
                        : "Esta aula gera cobranca unica no cartao quando for concluida."}
                    </p>
                  ) : null}
                  {!unlocked && currentUser?.role !== "admin" ? (
                    <p className="text-right text-xs leading-5 text-slate-400">
                      Esta aula abre quando a semana {lesson.release_week} estiver liberada e as anteriores forem concluidas.
                    </p>
                  ) : null}
                </div>
              </div>

              {unlocked ? (
                <div className="mt-6 grid gap-4 xl:grid-cols-2">
                  {(lesson.cards?.length ? lesson.cards : [{ title: "Conteudo", body: lesson.content, asset_type: "texto" }]).map((card, index) => (
                    <LessonCardDisplay
                      key={`${lesson.id}-${index}-${card.title}`}
                      card={{
                        title: card.title || `Card ${index + 1}`,
                        body: card.body ?? "",
                        asset_type: card.asset_type ?? "texto",
                        asset_url: card.asset_url ?? "",
                        button_label: card.button_label ?? "",
                      }}
                    />
                  ))}
                </div>
              ) : (
                <div className="mt-6 rounded-3xl border border-white/10 bg-slate-950/35 p-5">
                  <p className="text-sm leading-6 text-slate-300">
                    Esta aula esta protegida pela sequencia semanal. Quando chegar a vez dela, os cards aparecem aqui automaticamente.
                  </p>
                </div>
              )}
            </article>
          )
        })}
      </div>

      {paymentModalLesson ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/85 px-4 py-8 backdrop-blur-sm">
          <form className="glass-panel w-full max-w-2xl space-y-5 p-6" onSubmit={handlePaymentSubmit}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.35em] text-mango">cartao de credito</p>
                <h2 className="mt-2 text-2xl font-semibold text-white">Concluir aula com cobranca</h2>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  {paymentModalLesson.title} sera cobrada por {formatCurrency(paymentModalLesson.price)} no cartao de credito.
                </p>
              </div>
              <button className="soft-button-muted" onClick={closePaymentModal} type="button">
                Fechar
              </button>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <FieldInput
                label="Nome no cartao"
                onChange={(value) => setPaymentForm((prev) => ({ ...prev, card_holder_name: value }))}
                required
                value={paymentForm.card_holder_name}
              />
              <FieldInput
                label="Numero do cartao"
                inputMode="numeric"
                onChange={(value) => setPaymentForm((prev) => ({ ...prev, card_number: value }))}
                required
                value={paymentForm.card_number}
              />
              <FieldInput
                label="Mes de validade"
                max={12}
                min={1}
                onChange={(value) => setPaymentForm((prev) => ({ ...prev, expiry_month: value }))}
                required
                type="number"
                value={paymentForm.expiry_month}
              />
              <FieldInput
                label="Ano de validade"
                min={new Date().getFullYear()}
                onChange={(value) => setPaymentForm((prev) => ({ ...prev, expiry_year: value }))}
                required
                type="number"
                value={paymentForm.expiry_year}
              />
              <FieldInput
                label="CVV"
                inputMode="numeric"
                maxLength={4}
                onChange={(value) => setPaymentForm((prev) => ({ ...prev, cvv: value }))}
                required
                value={paymentForm.cvv}
              />
              <div className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 text-sm text-slate-200">
                <p className="font-medium text-white">Bandeira identificada</p>
                <p className="mt-1 text-slate-300">{paymentBrand}</p>
                <p className="mt-3 font-medium text-white">Valor desta aula</p>
                <p className="mt-1 text-mango">{formatCurrency(paymentModalLesson.price)}</p>
              </div>
            </div>

            <button className="soft-button-primary w-full" disabled={processingLessonId === paymentModalLesson.id} type="submit">
              {processingLessonId === paymentModalLesson.id
                ? "Autorizando cartao e concluindo..."
                : `Pagar ${formatCurrency(paymentModalLesson.price)} e concluir aula`}
            </button>
          </form>
        </div>
      ) : null}
    </div>
  )
}

function AdminStudioPage({
  courses,
  lessons,
  notice,
  onCreateCourse,
  onCreateLesson,
  onNotice,
  onSelectCourse,
  selectedCourseId,
}) {
  const [activeTab, setActiveTab] = useState("courses")
  const [creatingCourse, setCreatingCourse] = useState(false)
  const [creatingLesson, setCreatingLesson] = useState(false)
  const [courseForm, setCourseForm] = useState({
    title: "",
    description: "",
    category: "",
    cohort_name: "",
    start_date: "",
    end_date: "",
    capacity: 200,
    price: 0,
    is_paid: false,
  })
  const [lessonForm, setLessonForm] = useState({
    course_id: selectedCourseId ?? "",
    title: "",
    description: "",
    type: "video",
    order_index: "",
    price: 0,
    cards: [createEmptyLessonCard()],
  })

  const selectedCourse = courses.find((course) => String(course.id) === String(selectedCourseId))

  useEffect(() => {
    setLessonForm((prev) => ({
      ...prev,
      course_id: selectedCourseId ?? "",
      price:
        String(prev.course_id) === String(selectedCourseId)
          ? prev.price
          : selectedCourse?.is_paid
            ? Number(selectedCourse.price ?? 0)
            : 0,
    }))
  }, [selectedCourse, selectedCourseId])

  function updateLessonCard(cardIndex, patch) {
    setLessonForm((prev) => ({
      ...prev,
      cards: prev.cards.map((card, index) => {
        if (index !== cardIndex) return card
        const nextCard = { ...card, ...patch }
        if (patch.asset_type === "texto") {
          nextCard.asset_url = ""
          nextCard.button_label = ""
        }
        return nextCard
      }),
    }))
  }

  function addLessonCard() {
    setLessonForm((prev) => ({
      ...prev,
      cards: [...prev.cards, createEmptyLessonCard(prev.cards.length + 1)],
    }))
  }

  function removeLessonCard(cardIndex) {
    setLessonForm((prev) => ({
      ...prev,
      cards: prev.cards.filter((_, index) => index !== cardIndex),
    }))
  }

  async function handleCourseSubmit(event) {
    event.preventDefault()
    setCreatingCourse(true)
    try {
      const createdCourse = await onCreateCourse(courseForm)
      onNotice({ type: "success", text: "Curso cadastrado com sucesso no Studio Admin." })
      setCourseForm({
        title: "",
        description: "",
        category: "",
        cohort_name: "",
        start_date: "",
        end_date: "",
        capacity: 200,
        price: 0,
        is_paid: false,
      })
      setActiveTab("lessons")
      onSelectCourse(String(createdCourse.id))
    } catch (error) {
      onNotice({ type: "error", text: error.message })
    } finally {
      setCreatingCourse(false)
    }
  }

  async function handleLessonSubmit(event) {
    event.preventDefault()
    setCreatingLesson(true)
    try {
      const normalizedCards = lessonForm.cards.map((card, index) => ({
        title: card.title.trim() || `Card ${index + 1}`,
        body: card.body.trim() || "",
        asset_type: card.asset_type,
        asset_url: card.asset_url.trim() || "",
        button_label: card.button_label.trim() || "",
      }))
      const firstTextCard = normalizedCards.find((card) => card.asset_type === "texto" && card.body)

      await onCreateLesson({
        course_id: Number(lessonForm.course_id),
        title: lessonForm.title.trim(),
        description: lessonForm.description.trim(),
        type: lessonForm.type,
        order_index: lessonForm.order_index ? Number(lessonForm.order_index) : undefined,
        price: Number(lessonForm.price),
        content: firstTextCard?.body,
        cards: normalizedCards,
      })
      onNotice({ type: "success", text: "Aula publicada com cards multimidia." })
      setLessonForm((prev) => ({
        ...prev,
        title: "",
        description: "",
        order_index: "",
        price: selectedCourse?.is_paid ? Number(selectedCourse.price ?? 0) : 0,
        cards: [createEmptyLessonCard()],
      }))
    } catch (error) {
      onNotice({ type: "error", text: error.message })
    } finally {
      setCreatingLesson(false)
    }
  }

  return (
    <div className="page-enter space-y-6">
      <section className="grid gap-5 xl:grid-cols-[1.2fr,0.8fr]">
        <div className="glass-panel overflow-hidden p-8">
          <div className="mb-6 inline-flex rounded-full border border-white/10 bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.35em] text-surf">
            studio admin
          </div>
          <h1 className="max-w-3xl font-serif text-4xl text-white sm:text-5xl">
            Cadastre cursos e monte aulas em cards sem misturar operacao com experiencia do aluno.
          </h1>
          <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-300">
            O painel administrativo agora foi concentrado aqui. Voce escolhe a turma, define a janela do curso, informa o valor base por aula e monta cada aula com sua propria cobranca quando necessario.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <MiniPill title="Cursos isolados" text="Cadastro completo de turma, vagas, valor e periodo." />
            <MiniPill title="Aulas modulares" text="Cada aula nasce com um conjunto proprio de cards." />
            <MiniPill title="Preview rapido" text="O que voce publica aqui aparece na trilha do aluno." />
          </div>
        </div>

        <div className="grid gap-4">
          <StatCard label="Cursos publicados" value={courses.length} accent="from-surf to-cyan-400" />
          <StatCard
            label="Aulas do curso em foco"
            value={selectedCourseId ? lessons.length : 0}
            accent="from-mango to-coral"
          />
          <StatCard
            label="Cards do curso em foco"
            value={selectedCourseId ? lessons.reduce((acc, lesson) => acc + (lesson.cards?.length ?? 0), 0) : 0}
            accent="from-emerald-400 to-lime-300"
          />
        </div>
      </section>

      <div className="glass-panel flex flex-col gap-4 p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-3">
          {[
            ["courses", "Cursos"],
            ["lessons", "Aulas"],
          ].map(([key, label]) => (
            <button
              key={key}
              className={activeTab === key ? "soft-button-primary min-w-[140px]" : "soft-button-muted min-w-[140px]"}
              onClick={() => setActiveTab(key)}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
        <div className="w-full max-w-sm">
          <label className="mb-2 block text-sm font-medium text-slate-200">Curso em foco</label>
          <select className="soft-input" onChange={(event) => onSelectCourse(event.target.value)} value={selectedCourseId ?? ""}>
            <option value="">Selecione um curso</option>
            {courses.map((course) => (
              <option key={course.id} value={course.id}>
                {course.title}
              </option>
            ))}
          </select>
        </div>
      </div>

      {notice ? (
        <div
          className={`rounded-2xl border px-4 py-3 text-sm ${
            notice.type === "success"
              ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100"
              : "border-coral/40 bg-coral/10 text-rose-100"
          }`}
        >
          {notice.text}
        </div>
      ) : null}

      {activeTab === "courses" ? (
        <section className="grid gap-6 xl:grid-cols-[1.08fr,0.92fr]">
          <form className="glass-panel grid gap-4 p-6 lg:grid-cols-2" onSubmit={handleCourseSubmit}>
            <div className="lg:col-span-2">
              <h2 className="text-2xl font-semibold text-white">Cadastrar curso</h2>
              <p className="mt-1 text-sm text-slate-300">
                Defina turma, datas, capacidade maxima de 200 alunos e o valor base por aula para trilhas pagas.
              </p>
            </div>
            <FieldInput
              label="Titulo"
              required
              value={courseForm.title}
              onChange={(value) => setCourseForm((prev) => ({ ...prev, title: value }))}
            />
            <FieldInput
              label="Categoria"
              value={courseForm.category}
              onChange={(value) => setCourseForm((prev) => ({ ...prev, category: value }))}
            />
            <FieldInput
              label="Turma"
              required
              value={courseForm.cohort_name}
              onChange={(value) => setCourseForm((prev) => ({ ...prev, cohort_name: value }))}
            />
            <FieldInput
              label="Capacidade"
              min={1}
              max={200}
              required
              type="number"
              value={courseForm.capacity}
              onChange={(value) => setCourseForm((prev) => ({ ...prev, capacity: Number(value) }))}
            />
            <FieldInput
              label="Inicio"
              required
              type="date"
              value={courseForm.start_date}
              onChange={(value) => setCourseForm((prev) => ({ ...prev, start_date: value }))}
            />
            <FieldInput
              label="Fim"
              required
              type="date"
              value={courseForm.end_date}
              onChange={(value) => setCourseForm((prev) => ({ ...prev, end_date: value }))}
            />
            <div className="lg:col-span-2">
              <label className="mb-2 block text-sm font-medium text-slate-200">Descricao</label>
              <textarea
                className="soft-input min-h-28"
                required
                value={courseForm.description}
                onChange={(event) => setCourseForm((prev) => ({ ...prev, description: event.target.value }))}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-[1fr,auto] lg:col-span-2">
              <FieldInput
                label="Valor base por aula"
                min={0}
                step="0.01"
                type="number"
                value={courseForm.price}
                onChange={(value) => setCourseForm((prev) => ({ ...prev, price: Number(value), is_paid: Number(value) > 0 }))}
              />
              <label className="flex items-end gap-3 rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3 text-sm text-slate-200">
                <input
                  checked={courseForm.is_paid}
                  className="mt-1 h-4 w-4 accent-amber-400"
                  onChange={(event) => setCourseForm((prev) => ({ ...prev, is_paid: event.target.checked }))}
                  type="checkbox"
                />
                Curso pago
              </label>
            </div>
            <div className="lg:col-span-2">
              <button className="soft-button-primary w-full" disabled={creatingCourse} type="submit">
                {creatingCourse ? "Publicando curso..." : "Cadastrar curso"}
              </button>
            </div>
          </form>

          <div className="glass-panel p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold text-white">Cursos cadastrados</h2>
                <p className="mt-1 text-sm text-slate-300">Use esta lista para conferir turma, janela de matricula e valor publicado.</p>
              </div>
              <span className="rounded-full bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.25em] text-slate-200">
                {courses.length} cursos
              </span>
            </div>
            <div className="mt-5 space-y-4">
              {courses.length === 0 ? (
                <EmptyState title="Nenhum curso cadastrado" text="Comece criando a primeira turma para destravar a aba de aulas." />
              ) : (
                courses.map((course) => (
                  <button
                    key={course.id}
                    className={`w-full rounded-3xl border p-5 text-left transition ${
                      String(course.id) === String(selectedCourseId)
                        ? "border-surf/50 bg-surf/[0.08]"
                        : "border-white/10 bg-slate-950/35 hover:bg-white/[0.05]"
                    }`}
                    onClick={() => onSelectCourse(String(course.id))}
                    type="button"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h3 className="text-lg font-semibold text-white">{course.title}</h3>
                      <span className="rounded-full bg-mango/[0.15] px-3 py-1 text-xs uppercase tracking-[0.25em] text-mango">
                        {course.is_paid ? `${formatCurrency(course.price)} por aula` : "gratuito"}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-300">{course.description}</p>
                    <dl className="mt-4 space-y-2 text-sm text-slate-200">
                      <InfoRow label="Turma" value={course.cohort_name} />
                      <InfoRow label="Inicio" value={formatDate(course.start_date)} />
                      <InfoRow label="Janela" value={`${formatDate(course.enrollment_window_open)} ate ${formatDate(course.enrollment_window_close)}`} />
                      <InfoRow label="Capacidade" value={`${course.capacity} alunos`} />
                    </dl>
                  </button>
                ))
              )}
            </div>
          </div>
        </section>
      ) : (
        <section className="grid gap-6 xl:grid-cols-[1.05fr,0.95fr]">
          <form className="glass-panel space-y-5 p-6" onSubmit={handleLessonSubmit}>
            <div>
              <h2 className="text-2xl font-semibold text-white">Criar aula em cards</h2>
              <p className="mt-1 text-sm text-slate-300">
                Monte a aula como uma sequencia de blocos. Defina tambem se a conclusao da aula gera cobranca no cartao ou se ela sera gratuita.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="md:col-span-2">
                <label className="mb-2 block text-sm font-medium text-slate-200">Curso</label>
                <select
                  className="soft-input"
                  onChange={(event) => onSelectCourse(event.target.value)}
                  required
                  value={lessonForm.course_id}
                >
                  <option value="">Selecione um curso</option>
                  {courses.map((course) => (
                    <option key={course.id} value={course.id}>
                      {course.title}
                    </option>
                  ))}
                </select>
              </div>
              <FieldInput
                label="Titulo"
                required
                value={lessonForm.title}
                onChange={(value) => setLessonForm((prev) => ({ ...prev, title: value }))}
              />
              <FieldInput
                label="Ordem (1 a 40)"
                max={40}
                min={1}
                type="number"
                value={lessonForm.order_index}
                onChange={(value) => setLessonForm((prev) => ({ ...prev, order_index: value }))}
              />
              <FieldInput
                label="Preco da aula"
                min={0}
                step="0.01"
                type="number"
                value={lessonForm.price}
                onChange={(value) => setLessonForm((prev) => ({ ...prev, price: Number(value) }))}
              />
              <div>
                <label className="mb-2 block text-sm font-medium text-slate-200">Tipo</label>
                <select
                  className="soft-input"
                  onChange={(event) => setLessonForm((prev) => ({ ...prev, type: event.target.value }))}
                  value={lessonForm.type}
                >
                  <option value="video">Video</option>
                  <option value="texto">Texto</option>
                  <option value="atividade">Atividade</option>
                </select>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-950/35 px-4 py-3 text-sm text-slate-200">
                <p className="font-medium text-white">Regra aplicada automaticamente</p>
                <p className="mt-1 leading-6 text-slate-300">
                  A release semanal segue a ordem da aula, dentro do limite de 40 aulas por curso. Se o preco for maior que zero, a cobranca acontece no cartao ao concluir esta etapa.
                </p>
              </div>
              <div className="md:col-span-2">
                <label className="mb-2 block text-sm font-medium text-slate-200">Descricao</label>
                <textarea
                  className="soft-input min-h-24"
                  required
                  value={lessonForm.description}
                  onChange={(event) => setLessonForm((prev) => ({ ...prev, description: event.target.value }))}
                />
              </div>
            </div>

            <div className="rounded-3xl border border-white/10 bg-slate-950/30 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-lg font-semibold text-white">Cards da aula</h3>
                  <p className="mt-1 text-sm text-slate-300">Combine quantos blocos precisar para contar a historia da aula.</p>
                </div>
                <button className="soft-button-muted" onClick={addLessonCard} type="button">
                  Adicionar card
                </button>
              </div>
              <div className="mt-4 space-y-4">
                {lessonForm.cards.map((card, index) => (
                  <LessonCardEditor
                    key={`editor-${index}`}
                    card={card}
                    canRemove={lessonForm.cards.length > 1}
                    index={index}
                    onChange={updateLessonCard}
                    onRemove={removeLessonCard}
                  />
                ))}
              </div>
            </div>

            <button className="soft-button-primary w-full" disabled={creatingLesson} type="submit">
              {creatingLesson ? "Publicando aula..." : "Publicar aula"}
            </button>
          </form>

          <div className="space-y-6">
            <div className="glass-panel p-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h2 className="text-2xl font-semibold text-white">Curriculo em foco</h2>
                  <p className="mt-1 text-sm text-slate-300">
                    {selectedCourse ? `Cards publicados para ${selectedCourse.title}.` : "Selecione um curso para ver as aulas existentes."}
                  </p>
                </div>
                {selectedCourse ? (
                  <span className="rounded-full bg-white/[0.08] px-3 py-1 text-xs uppercase tracking-[0.25em] text-slate-200">
                    {lessons.length} aulas
                  </span>
                ) : null}
              </div>
              <div className="mt-5 space-y-4">
                {!selectedCourse ? (
                  <EmptyState title="Selecione um curso" text="Escolha a turma acima para iniciar a criacao de aulas e acompanhar o curriculo." />
                ) : lessons.length === 0 ? (
                  <EmptyState title="Sem aulas publicadas" text="A primeira aula desta turma pode ser montada agora com cards multimidia." />
                ) : (
                  lessons.map((lesson) => (
                    <article key={lesson.id} className="rounded-3xl border border-white/10 bg-slate-950/35 p-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
                            semana {lesson.release_week} - ordem {lesson.order_index}
                          </p>
                          <h3 className="mt-2 text-lg font-semibold text-white">{lesson.title}</h3>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full bg-mango/[0.15] px-3 py-1 text-xs uppercase tracking-[0.25em] text-mango">
                            {Number(lesson.price ?? 0) > 0 ? `${formatCurrency(lesson.price)} no cartao` : "sem cobranca"}
                          </span>
                          <span className="rounded-full bg-surf/[0.15] px-3 py-1 text-xs uppercase tracking-[0.25em] text-surf">
                            {lesson.cards?.length ?? 0} cards
                          </span>
                        </div>
                      </div>
                      <p className="mt-3 text-sm leading-6 text-slate-300">{lesson.description}</p>
                      <div className="mt-4 grid gap-3">
                        {(lesson.cards ?? []).map((card, index) => (
                          <LessonCardDisplay
                            key={`${lesson.id}-preview-${index}`}
                            card={{
                              title: card.title || `Card ${index + 1}`,
                              body: card.body ?? "",
                              asset_type: card.asset_type ?? "texto",
                              asset_url: card.asset_url ?? "",
                              button_label: card.button_label ?? "",
                            }}
                            compact
                          />
                        ))}
                      </div>
                    </article>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

function LessonCardEditor({ card, canRemove, index, onChange, onRemove }) {
  return (
    <article className="rounded-3xl border border-white/10 bg-slate-950/45 p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-slate-400">card {index + 1}</p>
          <h4 className="mt-1 text-lg font-semibold text-white">{card.title || `Card ${index + 1}`}</h4>
        </div>
        <button className="soft-button-muted" disabled={!canRemove} onClick={() => onRemove(index)} type="button">
          Remover
        </button>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <FieldInput label="Titulo do card" value={card.title} onChange={(value) => onChange(index, { title: value })} />
        <div>
          <label className="mb-2 block text-sm font-medium text-slate-200">Tipo de recurso</label>
          <select
            className="soft-input"
            onChange={(event) => onChange(index, { asset_type: event.target.value })}
            value={card.asset_type}
          >
            {LESSON_CARD_TYPES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="mb-2 block text-sm font-medium text-slate-200">
            {card.asset_type === "texto" ? "Conteudo do card" : "Texto de apoio ou contexto"}
          </label>
          <textarea
            className="soft-input min-h-24"
            onChange={(event) => onChange(index, { body: event.target.value })}
            value={card.body}
          />
        </div>
        {card.asset_type !== "texto" ? (
          <>
            <FieldInput
              label="URL do recurso"
              placeholder="https://..."
              value={card.asset_url}
              onChange={(value) => onChange(index, { asset_url: value })}
            />
            <FieldInput
              label="Texto do botao (opcional)"
              placeholder="Abrir material"
              value={card.button_label}
              onChange={(value) => onChange(index, { button_label: value })}
            />
          </>
        ) : null}
      </div>

      <p className="mt-3 text-xs leading-5 text-slate-400">{getCardTypeHint(card.asset_type)}</p>

      <div className="mt-4">
        <p className="mb-2 text-xs uppercase tracking-[0.3em] text-slate-500">preview</p>
        <LessonCardDisplay card={card} compact />
      </div>
    </article>
  )
}

function LessonCardDisplay({ card, compact = false }) {
  const body = card.body?.trim()
  const assetUrl = card.asset_url?.trim()
  const buttonLabel =
    card.button_label?.trim() ||
    (card.asset_type === "pdf"
      ? "Abrir PDF"
      : card.asset_type === "video"
        ? "Abrir video"
        : card.asset_type === "imagem"
          ? "Abrir imagem"
          : "Abrir recurso")

  return (
    <article className={`rounded-3xl border border-white/10 bg-slate-950/40 ${compact ? "p-4" : "p-5"}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className={`${compact ? "text-base" : "text-lg"} font-semibold text-white`}>{card.title || "Card"}</h3>
        <span className="rounded-full bg-white/[0.08] px-3 py-1 text-[11px] uppercase tracking-[0.24em] text-slate-300">
          {CARD_TYPE_LABELS[card.asset_type] ?? "Card"}
        </span>
      </div>

      {body ? <p className="mt-3 text-sm leading-6 text-slate-300">{body}</p> : null}

      {card.asset_type !== "texto" && assetUrl ? <div className="mt-4"><LessonAssetPreview card={card} compact={compact} /></div> : null}

      {card.asset_type !== "texto" && assetUrl ? (
        <a className="soft-button-muted mt-4 w-full" href={assetUrl} rel="noreferrer" target="_blank">
          {buttonLabel}
        </a>
      ) : null}
    </article>
  )
}

function LessonAssetPreview({ card, compact = false }) {
  const assetUrl = card.asset_url?.trim()

  if (!assetUrl) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.03] p-4 text-sm text-slate-400">
        Adicione uma URL para visualizar o recurso.
      </div>
    )
  }

  if (card.asset_type === "imagem") {
    return <img alt={card.title || "Imagem da aula"} className={`w-full rounded-2xl object-cover ${compact ? "max-h-56" : "max-h-[360px]"}`} src={assetUrl} />
  }

  if (card.asset_type === "video") {
    if (isDirectVideo(assetUrl)) {
      return <video className={`w-full rounded-2xl bg-slate-950 ${compact ? "max-h-56" : "max-h-[360px]"}`} controls src={assetUrl} />
    }

    return (
      <iframe
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        className={`w-full rounded-2xl border border-white/10 bg-slate-950 ${compact ? "min-h-[220px]" : "min-h-[320px]"}`}
        src={toEmbeddableUrl(assetUrl)}
        title={card.title || "Video da aula"}
      />
    )
  }

  if (card.asset_type === "pdf" || card.asset_type === "embed") {
    return (
      <iframe
        className={`w-full rounded-2xl border border-white/10 bg-slate-950 ${compact ? "min-h-[260px]" : "min-h-[380px]"}`}
        src={card.asset_type === "embed" ? toEmbeddableUrl(assetUrl) : assetUrl}
        title={card.title || "Conteudo incorporado"}
      />
    )
  }

  if (card.asset_type === "link") {
    return (
      <div className="rounded-2xl border border-dashed border-surf/30 bg-surf/[0.08] p-4 text-sm leading-6 text-slate-200">
        Link externo pronto para abrir em uma nova aba.
      </div>
    )
  }

  return null
}

function ProgressPage({
  adminCourseProgress,
  adminProgressError,
  adminProgressLoading,
  courses,
  currentUser,
  onSelectCourse,
  progress,
  selectedCourseId,
}) {
  if (currentUser?.role === "admin") {
    const selectedCourse = courses.find((course) => String(course.id) === String(selectedCourseId))
    const averageProgress =
      adminCourseProgress.length > 0
        ? Math.round(adminCourseProgress.reduce((acc, item) => acc + item.percentage, 0) / adminCourseProgress.length)
        : 0
    const completedStudents = adminCourseProgress.filter((item) => item.percentage >= 100).length

    return (
      <div className="page-enter space-y-6">
        <section className="grid gap-5 lg:grid-cols-[1.25fr,0.75fr]">
          <div className="glass-panel p-6">
            <h1 className="text-3xl font-semibold text-white">Progresso por aluno</h1>
            <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-300">
              Escolha uma turma para acompanhar a barra de progresso individual, a proxima aula de cada aluno e o ritmo geral da trilha.
            </p>
          </div>
          <div className="grid gap-4">
            <StatCard label="Matriculados" value={adminCourseProgress.length} accent="from-surf to-cyan-400" />
            <StatCard label="Media da turma" value={`${averageProgress}%`} accent="from-mango to-coral" />
            <StatCard label="Concluiram tudo" value={completedStudents} accent="from-emerald-400 to-lime-300" />
          </div>
        </section>

        <section className="glass-panel p-6">
          <div className="grid gap-4 lg:grid-cols-[1fr,320px] lg:items-end">
            <div>
              <h2 className="text-2xl font-semibold text-white">Turma em foco</h2>
              <p className="mt-1 text-sm text-slate-300">
                {selectedCourse
                  ? `Acompanhando ${selectedCourse.title} para enxergar a evolucao aluno por aluno.`
                  : "Selecione um curso para liberar a leitura individual da turma."}
              </p>
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-200">Curso</label>
              <select className="soft-input" onChange={(event) => onSelectCourse(event.target.value)} value={selectedCourseId ?? ""}>
                <option value="">Selecione um curso</option>
                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.title}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </section>

        {adminProgressError ? (
          <div className="rounded-2xl border border-coral/40 bg-coral/10 px-4 py-3 text-sm text-rose-100">{adminProgressError}</div>
        ) : null}

        {!selectedCourseId ? (
          <EmptyState title="Selecione um curso" text="Assim que a turma for escolhida, as barras de progresso dos alunos aparecem aqui." />
        ) : adminProgressLoading ? (
          <div className="glass-panel flex min-h-[24vh] items-center justify-center p-10 text-slate-200">Carregando progresso da turma...</div>
        ) : adminCourseProgress.length === 0 ? (
          <EmptyState title="Nenhum aluno matriculado" text="Quando houver matriculas nesta turma, o progresso individual sera listado aqui." />
        ) : (
          <section className="grid gap-5 xl:grid-cols-2">
            {adminCourseProgress.map((item) => (
              <article key={item.enrollment_id} className="glass-panel p-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
                      grupo {item.group_number} - {item.status}
                    </p>
                    <h2 className="mt-2 text-2xl font-semibold text-white">{item.student_name}</h2>
                    <p className="mt-1 text-sm text-slate-300">{item.student_email || item.student_cpf}</p>
                  </div>
                  <span className="rounded-full bg-surf/[0.15] px-3 py-1 text-xs uppercase tracking-[0.25em] text-surf">
                    {item.percentage}%
                  </span>
                </div>
                <div className="mt-5">
                  <ProgressMeter percentage={item.percentage} />
                </div>
                <dl className="mt-5 space-y-2 text-sm text-slate-200">
                  <InfoRow label="Concluidas" value={`${item.completed_lessons}/${item.total_lessons}`} />
                  <InfoRow label="Liberadas" value={item.available_lessons} />
                  <InfoRow label="Proxima aula" value={item.next_lesson || "Curso finalizado"} />
                  <InfoRow label="CPF" value={item.student_cpf} />
                  <InfoRow label="Acesso ate" value={formatDate(item.access_expires_at)} />
                </dl>
              </article>
            ))}
          </section>
        )}
      </div>
    )
  }

  return (
    <div className="page-enter space-y-6">
      <div className="glass-panel p-6">
        <h1 className="text-3xl font-semibold text-white">Progresso consolidado</h1>
        <p className="mt-2 text-sm text-slate-300">
          Veja o percentual, a proxima aula e o periodo restante de acesso em cada curso.
        </p>
      </div>

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {progress.length === 0 ? (
          <EmptyState title="Sem progresso ainda" text="O indicador aparece assim que houver matriculas ativas e aulas cadastradas." />
        ) : (
          progress.map((item) => (
            <article key={item.course_id} className="glass-panel p-6">
              <div className="flex items-center justify-between gap-4">
                <h2 className="text-2xl font-semibold text-white">{item.course_title}</h2>
                <span className="rounded-full bg-surf/[0.15] px-3 py-1 text-xs uppercase tracking-[0.25em] text-surf">
                  {item.percentage}%
                </span>
              </div>
              <div className="mt-5">
                <ProgressMeter percentage={item.percentage} />
              </div>
              <dl className="mt-5 space-y-2 text-sm text-slate-200">
                <InfoRow label="Concluidas" value={`${item.completed_lessons}/${item.total_lessons}`} />
                <InfoRow label="Liberadas" value={item.available_lessons} />
                <InfoRow label="Proxima aula" value={item.next_lesson || "Curso finalizado"} />
                <InfoRow label="Acesso ate" value={formatDate(item.access_expires_at)} />
              </dl>
            </article>
          ))
        )}
      </section>
    </div>
  )
}

function LoginPage({ onLogin, onRegister, loading, notice, onNotice }) {
  const [mode, setMode] = useState("login")
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    role: "aluno",
    admin_code: "",
  })

  async function handleSubmit(event) {
    event.preventDefault()
    try {
      if (mode === "login") {
        await onLogin({ email: form.email, password: form.password })
        return
      }
      await onRegister(form)
    } catch (error) {
      onNotice({ type: "error", text: error.message })
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(255,179,71,0.18),transparent_22%),radial-gradient(circle_at_85%_15%,rgba(110,231,249,0.14),transparent_22%),radial-gradient(circle_at_50%_100%,rgba(255,127,80,0.16),transparent_25%)]" />
      <div className="relative grid w-full max-w-6xl gap-6 lg:grid-cols-[1.1fr,0.9fr]">
        <section className="glass-panel p-8 lg:p-10">
          <p className="rounded-full border border-white/10 bg-white/[0.08] px-4 py-2 text-xs uppercase tracking-[0.35em] text-surf">
            ead orbit
          </p>
          <h1 className="mt-6 max-w-2xl font-serif text-5xl text-white">
            Microservicos prontos para operar cursos, aulas e progresso sem friccao.
          </h1>
          <p className="mt-5 max-w-xl text-sm leading-7 text-slate-300">
            A plataforma combina autenticacao JWT, gateway central, bancos PostgreSQL isolados e uma experiencia React para acompanhar toda a jornada do aluno.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <MiniPill title="Gateway unico" text="Rotas centralizadas para os 7 servicos." />
            <MiniPill title="Janela de matricula" text="Valida 5 a 1 semanas antes do inicio." />
            <MiniPill title="Liberacao semanal" text="A ordem das aulas e protegida por regra." />
          </div>
        </section>

        <form className="glass-panel p-8" onSubmit={handleSubmit}>
          <div className="mb-6 flex gap-3">
            <button
              className={mode === "login" ? "soft-button-primary flex-1" : "soft-button-muted flex-1"}
              onClick={() => setMode("login")}
              type="button"
            >
              Entrar
            </button>
            <button
              className={mode === "register" ? "soft-button-primary flex-1" : "soft-button-muted flex-1"}
              onClick={() => setMode("register")}
              type="button"
            >
              Criar conta
            </button>
          </div>

          <h2 className="text-3xl font-semibold text-white">{mode === "login" ? "Acesse sua area" : "Abra sua conta"}</h2>
          <p className="mt-2 text-sm text-slate-300">
            {mode === "login"
              ? "Use email e senha para entrar no dashboard."
              : "Cadastre um novo usuario. Para admin, informe o codigo administrativo configurado no ambiente."}
          </p>

          {notice ? (
            <div
              className={`mt-5 rounded-2xl border px-4 py-3 text-sm ${
                notice.type === "success"
                  ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-100"
                  : "border-coral/40 bg-coral/10 text-rose-100"
              }`}
            >
              {notice.text}
            </div>
          ) : null}

          <div className="mt-6 space-y-4">
            {mode === "register" ? (
              <FieldInput
                label="Nome"
                minLength={3}
                onChange={(value) => setForm((prev) => ({ ...prev, name: value }))}
                required
                value={form.name}
              />
            ) : null}
            <FieldInput
              label="Email"
              onChange={(value) => setForm((prev) => ({ ...prev, email: value }))}
              required
              type="email"
              value={form.email}
            />
            <FieldInput
              label="Senha"
              minLength={6}
              type="password"
              value={form.password}
              onChange={(value) => setForm((prev) => ({ ...prev, password: value }))}
              required
            />
            {mode === "register" ? (
              <>
                <div>
                  <label className="mb-2 block text-sm font-medium text-slate-200">Perfil</label>
                  <select
                    className="soft-input"
                    onChange={(event) => setForm((prev) => ({ ...prev, role: event.target.value }))}
                    value={form.role}
                  >
                    <option value="aluno">Aluno</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                {form.role === "admin" ? (
                  <FieldInput
                    label="Codigo administrativo"
                    required
                    value={form.admin_code}
                    onChange={(value) => setForm((prev) => ({ ...prev, admin_code: value }))}
                  />
                ) : null}
              </>
            ) : null}
          </div>

          <button className="soft-button-primary mt-8 w-full" disabled={loading} type="submit">
            {loading ? "Processando..." : mode === "login" ? "Entrar na plataforma" : "Criar conta e entrar"}
          </button>
        </form>
      </div>
    </div>
  )
}

function AppShell() {
  const navigate = useNavigate()
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? "")
  const [loading, setLoading] = useState(Boolean(token))
  const [currentUser, setCurrentUser] = useState(null)
  const [profile, setProfile] = useState(null)
  const [courses, setCourses] = useState([])
  const [enrollments, setEnrollments] = useState([])
  const [progress, setProgress] = useState([])
  const [payments, setPayments] = useState([])
  const [lessons, setLessons] = useState([])
  const [selectedCourseId, setSelectedCourseId] = useState("")
  const [adminCourseProgress, setAdminCourseProgress] = useState([])
  const [adminProgressLoading, setAdminProgressLoading] = useState(false)
  const [adminProgressError, setAdminProgressError] = useState("")
  const [notice, setNotice] = useState(null)

  async function hydrateSession(activeToken) {
    const me = await apiFetch("/auth/me", { token: activeToken })
    const userId = String(me.id)
    const [profileList, coursesList, enrollmentList, progressList, paymentList] = await Promise.all([
      apiFetch(`/users?auth_user_id=${userId}`, { token: activeToken }),
      apiFetch("/courses", { token: activeToken }),
      apiFetch(`/enrollments/user/${userId}`, { token: activeToken }),
      apiFetch(`/progress/${userId}`, { token: activeToken }),
      apiFetch(`/payments/${userId}`, { token: activeToken }),
    ])

    startTransition(() => {
      setCurrentUser(me)
      setProfile(profileList[0] ?? null)
      setCourses(coursesList)
      setEnrollments(enrollmentList)
      setProgress(progressList)
      setPayments(paymentList)
      if (!selectedCourseId) {
        const firstCourseId = (enrollmentList[0]?.course_id ?? coursesList[0]?.id ?? "").toString()
        setSelectedCourseId(firstCourseId)
      }
    })

    return me
  }

  async function refreshSession(activeToken = token) {
    if (!activeToken) return
    setLoading(true)
    try {
      await hydrateSession(activeToken)
    } catch (error) {
      localStorage.removeItem(TOKEN_KEY)
      setToken("")
      setCurrentUser(null)
      setProfile(null)
      setCourses([])
      setEnrollments([])
      setProgress([])
      setPayments([])
      setLessons([])
      setAdminCourseProgress([])
      setAdminProgressLoading(false)
      setAdminProgressError("")
      setNotice({ type: "error", text: error.message })
      navigate("/login")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (token) {
      refreshSession(token)
    }
  }, [])

  useEffect(() => {
    async function loadLessons() {
      if (!token || !selectedCourseId) {
        setLessons([])
        return
      }
      try {
        const data = await apiFetch(`/lessons/course/${selectedCourseId}`, { token })
        setLessons(data)
      } catch {
        setLessons([])
      }
    }

    loadLessons()
  }, [selectedCourseId, token])

  useEffect(() => {
    let cancelled = false

    async function loadAdminCourseProgress() {
      if (!token || currentUser?.role !== "admin" || !selectedCourseId) {
        setAdminCourseProgress([])
        setAdminProgressError("")
        setAdminProgressLoading(false)
        return
      }

      setAdminProgressLoading(true)
      setAdminProgressError("")
      try {
        const data = await apiFetch(`/progress/course/${selectedCourseId}/students`, { token })
        if (cancelled) return
        startTransition(() => {
          setAdminCourseProgress(data)
          setAdminProgressError("")
        })
      } catch (error) {
        if (cancelled) return
        startTransition(() => {
          setAdminCourseProgress([])
          setAdminProgressError(error.message)
        })
      } finally {
        if (!cancelled) {
          setAdminProgressLoading(false)
        }
      }
    }

    loadAdminCourseProgress()
    return () => {
      cancelled = true
    }
  }, [currentUser?.role, selectedCourseId, token])

  async function handleLogin(credentials) {
    setLoading(true)
    try {
      const data = await apiFetch("/auth/login", { method: "POST", body: credentials })
      localStorage.setItem(TOKEN_KEY, data.access_token)
      setToken(data.access_token)
      const me = await hydrateSession(data.access_token)
      setNotice({ type: "success", text: "Sessao iniciada com sucesso." })
      navigate(getDefaultRoute(me))
    } finally {
      setLoading(false)
    }
  }

  async function handleRegister(payload) {
    setLoading(true)
    try {
      await apiFetch("/auth/register", { method: "POST", body: payload })
      await handleLogin({ email: payload.email, password: payload.password })
      setNotice({ type: "success", text: "Conta criada e autenticada." })
    } finally {
      setLoading(false)
    }
  }

  async function handleSaveProfile(form) {
    const payload = {
      auth_user_id: String(currentUser.id),
      cpf: form.cpf,
      name: form.name,
      email: form.email,
      whatsapp: form.whatsapp,
      telegram: form.telegram,
      city: form.city,
      state: form.state,
      education_level: form.education_level,
    }

    if (profile?.id) {
      await apiFetch(`/users/${profile.id}`, { token, method: "PUT", body: payload })
    } else {
      await apiFetch("/users", { token, method: "POST", body: payload })
    }
    await refreshSession()
  }

  async function handleEnroll(course) {
    if (currentUser?.role !== "admin" && !profile?.cpf) {
      throw new Error("Complete o perfil com CPF antes de se matricular.")
    }

    const cpf = profile?.cpf
    await apiFetch("/enrollments", {
      token,
      method: "POST",
      body: {
        course_id: course.id,
        cpf,
      },
    })
    await refreshSession()
    setNotice({ type: "success", text: `Matricula confirmada em ${course.title}.` })
    navigate("/dashboard")
  }

  async function handleCreateCourse(courseForm) {
    const createdCourse = await apiFetch("/courses", {
      token,
      method: "POST",
      body: {
        ...courseForm,
        price: Number(courseForm.price),
        capacity: Number(courseForm.capacity),
      },
    })
    await refreshSession()
    setSelectedCourseId(String(createdCourse.id))
    return createdCourse
  }

  async function handleCreateLesson(lessonForm) {
    const courseId = String(lessonForm.course_id)
    const createdLesson = await apiFetch("/lessons", { token, method: "POST", body: lessonForm })
    const data = await apiFetch(`/lessons/course/${courseId}`, { token })
    setSelectedCourseId(courseId)
    setLessons(data)
    return createdLesson
  }

  async function handleCompleteLesson(courseId, lessonId, extraPayload) {
    await apiFetch("/progress", {
      token,
      method: "POST",
      body: {
        user_id: String(currentUser.id),
        course_id: courseId,
        lesson_id: lessonId,
        ...(extraPayload ?? {}),
      },
    })
    await refreshSession()
    const data = await apiFetch(`/lessons/course/${courseId}`, { token })
    setLessons(data)
    setNotice({ type: "success", text: extraPayload?.payment ? "Pagamento aprovado e progresso atualizado." : "Progresso atualizado." })
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY)
    setToken("")
    setCurrentUser(null)
    setProfile(null)
    setCourses([])
    setEnrollments([])
    setProgress([])
    setPayments([])
    setLessons([])
    setAdminCourseProgress([])
    setAdminProgressLoading(false)
    setAdminProgressError("")
    setNotice(null)
    navigate("/login")
  }

  if (!token) {
    return (
      <Routes>
        <Route
          element={
            <LoginPage
              loading={loading}
              notice={notice}
              onLogin={handleLogin}
              onNotice={setNotice}
              onRegister={handleRegister}
            />
          }
          path="*"
        />
      </Routes>
    )
  }

  const navItems =
    currentUser?.role === "admin"
      ? [
          ["/admin", "Studio Admin"],
          ["/dashboard", "Visao geral"],
          ["/courses", "Cursos"],
          ["/lessons", "Aulas"],
          ["/progress", "Progresso da turma"],
        ]
      : [
          ["/dashboard", "Dashboard"],
          ["/courses", "Cursos"],
          ["/lessons", "Aulas"],
          ["/progress", "Progresso"],
        ]

  return (
    <div className="min-h-screen">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-6 px-4 py-5 lg:flex-row lg:px-6">
        <aside className="glass-panel h-fit w-full p-5 lg:sticky lg:top-5 lg:w-72">
          <div className="rounded-3xl bg-gradient-to-br from-surf/20 via-white/5 to-mango/20 p-5">
            <p className="text-xs uppercase tracking-[0.35em] text-surf">ead orbit</p>
            <h1 className="mt-3 text-2xl font-semibold text-white">{currentUser?.name}</h1>
            <p className="mt-1 text-sm text-slate-300">{currentUser?.role}</p>
          </div>
          <nav className="mt-6 space-y-2">
            {navItems.map(([href, label]) => (
              <NavLink
                key={href}
                className={({ isActive }) =>
                  `block rounded-2xl px-4 py-3 text-sm font-semibold transition ${
                    isActive ? "bg-white text-slate-950" : "bg-white/[0.06] text-slate-200 hover:bg-white/10"
                  }`
                }
                to={href}
              >
                {label}
              </NavLink>
            ))}
          </nav>
          <button className="soft-button-muted mt-6 w-full" onClick={handleLogout} type="button">
            Sair
          </button>
        </aside>

        <main className="flex-1 py-1">
          {loading ? (
            <div className="glass-panel flex min-h-[40vh] items-center justify-center p-10 text-slate-200">
              Carregando painel...
            </div>
          ) : (
            <Routes>
              <Route
                element={
                  <DashboardPage
                    courses={courses}
                    currentUser={currentUser}
                    enrollments={enrollments}
                    notice={notice}
                    onNotice={setNotice}
                    onSaveProfile={handleSaveProfile}
                    payments={payments}
                    profile={profile}
                    progress={progress}
                  />
                }
                path="/dashboard"
              />
              <Route
                element={
                  <CoursesPage
                    courses={courses}
                    currentUser={currentUser}
                    enrollments={enrollments}
                    notice={notice}
                    onEnroll={handleEnroll}
                    profile={profile}
                  />
                }
                path="/courses"
              />
              <Route
                element={
                  <LessonsPage
                    courses={courses}
                    currentUser={currentUser}
                    enrollments={enrollments}
                    lessons={lessons}
                    notice={notice}
                    onCompleteLesson={handleCompleteLesson}
                    onNotice={setNotice}
                    onSelectCourse={setSelectedCourseId}
                    payments={payments}
                    progress={progress}
                    selectedCourseId={selectedCourseId}
                  />
                }
                path="/lessons"
              />
              <Route
                element={
                  currentUser?.role === "admin" ? (
                    <AdminStudioPage
                      courses={courses}
                      lessons={lessons}
                      notice={notice}
                      onCreateCourse={handleCreateCourse}
                      onCreateLesson={handleCreateLesson}
                      onNotice={setNotice}
                      onSelectCourse={setSelectedCourseId}
                      selectedCourseId={selectedCourseId}
                    />
                  ) : (
                    <Navigate replace to="/dashboard" />
                  )
                }
                path="/admin"
              />
              <Route
                element={
                  <ProgressPage
                    adminCourseProgress={adminCourseProgress}
                    adminProgressError={adminProgressError}
                    adminProgressLoading={adminProgressLoading}
                    courses={courses}
                    currentUser={currentUser}
                    onSelectCourse={setSelectedCourseId}
                    progress={progress}
                    selectedCourseId={selectedCourseId}
                  />
                }
                path="/progress"
              />
              <Route element={<Navigate replace to={getDefaultRoute(currentUser)} />} path="*" />
            </Routes>
          )}
        </main>
      </div>
    </div>
  )
}

function App() {
  return <AppShell />
}

function StatCard({ label, value, accent }) {
  return (
    <article className={`rounded-3xl bg-gradient-to-br ${accent} p-[1px]`}>
      <div className="rounded-[calc(1.5rem-1px)] bg-slate-950/90 p-5">
        <p className="text-xs uppercase tracking-[0.3em] text-slate-400">{label}</p>
        <p className="mt-4 text-3xl font-semibold text-white">{value}</p>
      </div>
    </article>
  )
}

function FieldInput({ label, onChange, type = "text", value, ...inputProps }) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-slate-200">{label}</label>
      <input
        className="soft-input"
        onChange={(event) => onChange(event.target.value)}
        type={type}
        value={value}
        {...inputProps}
      />
    </div>
  )
}

function InfoRow({ label, value }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-slate-400">{label}</dt>
      <dd className="text-right text-white">{value}</dd>
    </div>
  )
}

function ProgressMeter({ percentage }) {
  const clampedPercentage = Math.max(0, Math.min(100, Number(percentage ?? 0)))

  return (
    <div className="h-3 overflow-hidden rounded-full bg-white/10">
      <div
        className="h-full rounded-full bg-gradient-to-r from-surf to-mango transition-[width] duration-500"
        style={{ width: `${clampedPercentage}%` }}
      />
    </div>
  )
}

function EmptyState({ title, text }) {
  return (
    <div className="glass-panel p-6 text-center">
      <h3 className="text-xl font-semibold text-white">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-300">{text}</p>
    </div>
  )
}

function MiniPill({ title, text }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-slate-950/40 p-4">
      <p className="text-sm font-semibold text-white">{title}</p>
      <p className="mt-2 text-xs leading-6 text-slate-300">{text}</p>
    </div>
  )
}

export default App
