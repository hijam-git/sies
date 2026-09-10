# 06 — System Diagrams

The whole system in pictures. Every diagram is Mermaid, so it renders in GitHub,
VS Code and most markdown viewers without any tooling.

Scope note: diagrams marked **V1** show only what `05-scope-and-v1.md` puts in
the first release. Where a V2 element appears for context it is drawn dashed or
labelled.

**Index**

| # | Diagram | Answers |
|---|---------|---------|
| 1 | [System landscape](#1-system-landscape) | What runs, and what talks to what |
| 2 | [Module dependencies](#2-module-dependencies) | Which app may import which |
| 3 | [The yearly loop](#3-the-yearly-loop) | What the institution actually does |
| 4 | [Request lifecycle](#4-request-lifecycle--the-four-gates) | How one API call is authorised |
| 5 | [Branch scope resolution](#5-branch-scope-resolution) | Whose data does this request see |
| 6 | [Permission resolution](#6-permission-resolution) | Can this user do this verb |
| 7 | [Admission to enrolment](#7-admission--enrolment) | How a person becomes a student |
| 8 | [Fee lifecycle](#8-fee-lifecycle-state-machine) | The states an invoice moves through |
| 9 | [Monthly fee generation](#9-monthly-fee-generation-celery) | How fees raise themselves |
| 10 | [Fee collection at the counter](#10-fee-collection-at-the-counter) | The money path, and the auto-posted income |
| 11 | [Attendance month grid](#11-attendance-month-grid) | The teacher's daily screen |
| 12 | [Examination to result](#12-examination--result) | Marks in, marksheet out |
| 13 | [Entity relationships](#13-entity-relationships-v1) | The V1 data model |
| 14 | [Scheduled jobs](#14-scheduled-background-jobs) | What happens without anyone clicking |
| 15 | [UI navigation map](#15-ui-navigation-map) | Every screen, and who sees it |

---

## 1. System landscape

Seven containers. Only Traefik binds a host port — that is the security
boundary (`01` §2).

```mermaid
flowchart TB
    subgraph users["People"]
        A1["Platform Admin"]
        A2["Principal<br/>Accountant"]
        A3["Teacher"]
        A4["Student"]
    end

    A1 & A2 & A3 & A4 -->|"HTTPS"| TR

    subgraph edge["Edge"]
        TR["<b>Traefik</b><br/>:80 / :443<br/>TLS, the only exposed port"]
    end

    TR -->|"/api/*"| BE["<b>backend</b><br/>Django + DRF<br/>gunicorn"]
    TR -->|"everything else"| FE["<b>admin_dashboard</b><br/>React SPA, static"]

    BE --> PG[("<b>PostgreSQL</b><br/>the truth")]
    BE --> RD[("<b>Redis</b><br/>broker + results")]
    BE --> MV[("<b>media volume</b><br/>photos, documents")]

    RD --- CW["<b>celery-worker</b><br/>fees, reports, exports"]
    RD --- CB["<b>celery-beat</b><br/>the clock"]
    CW --> PG
    CW --> MV
    CB --> RD

    classDef edgeC fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef appC fill:#1f4a3a,stroke:#3fa37a,color:#fff
    classDef dataC fill:#4a3a1f,stroke:#c9a227,color:#fff
    classDef workC fill:#4a1f3a,stroke:#c05299,color:#fff
    class TR edgeC
    class BE,FE appC
    class PG,RD,MV dataC
    class CW,CB workC
```

## 2. Module dependencies

One-way only. A cycle here is what turns a Django project into a ball of mud, so
this ordering is a rule, not an observation (`01` §6).

```mermaid
flowchart LR
    CORE["core<br/><i>settings, celery, middleware</i>"]
    ACC["accounts<br/><i>User, Role, permissions</i>"]
    BR["branches<br/><i>Branch, Stream, Session</i>"]
    AKA["academics<br/><i>Class, Section, Subject, Enrolment</i>"]
    ST["students"]
    STF["staff"]
    ATT["attendance"]
    FEE["fees"]
    FIN["finance"]
    EX["exams"]
    RPT["reports<br/><i>screens only in V1</i>"]

    CORE --> ACC & BR
    ACC --> BR
    BR --> AKA & ST & STF & FEE & FIN
    AKA --> ST & ATT & FEE & EX
    ST --> ATT & FEE & EX
    STF --> ATT
    FEE -->|"a payment posts<br/>an income row"| FIN
    ATT & FEE & FIN & EX --> RPT

    classDef base fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef mid fill:#1f4a3a,stroke:#3fa37a,color:#fff
    classDef money fill:#4a3a1f,stroke:#c9a227,color:#fff
    classDef sink fill:#3a2a4a,stroke:#9b7fc4,color:#fff
    class CORE,ACC,BR base
    class AKA,ST,STF,ATT,EX mid
    class FEE,FIN money
    class RPT sink
```

`reports` reads from everything and is read by nothing. `fees → finance` is the
only cross-module write, and it never goes the other way.

## 3. The yearly loop

This is the software. Every screen sits on top of this loop, and it is the test
for whether a feature belongs in V1: *does the loop complete without it?*
(`05` §2)

```mermaid
flowchart TB
    S1["<b>Session opens</b><br/>2026 / 1447"]
    S2["Classes and sections defined<br/>per stream"]
    S3["Fee amounts set<br/>per class"]
    S4["<b>Admissions</b><br/>applications screened"]
    S5["<b>Enrolment</b><br/>student placed in class + section<br/>admission no. and roll issued"]

    D1["<b>DAILY</b><br/>attendance marked<br/>fees collected at the counter"]
    M1["<b>MONTHLY</b><br/>fees generate themselves<br/>salary paid"]
    P1["<b>PERIODIC</b><br/>exams, marks, results"]

    E1["<b>Session closes</b>"]
    E2["Promotion to next class"]

    S1 --> S2 --> S3 --> S4 --> S5
    S5 --> D1 & M1 & P1
    D1 & M1 & P1 --> E1
    E1 --> E2
    E2 -->|"new Enrolment,<br/>same Student"| S1

    classDef setup fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef loop fill:#1f4a3a,stroke:#3fa37a,color:#fff
    classDef close fill:#4a2a2a,stroke:#c46b6b,color:#fff
    class S1,S2,S3,S4,S5 setup
    class D1,M1,P1 loop
    class E1,E2 close
```

Note the return edge: promotion creates a **new Enrolment for the same Student**.
That is the entire reason `Enrolment` exists as a table (`05` §3.2).

## 4. Request lifecycle — the four gates

Order matters. Authentication says *who*; branch scoping says *which branch's
data exists at all*; the permission class says *what verb*; the queryset filter
is the belt-and-braces that turns a forgotten check into a 404 rather than a leak.

```mermaid
flowchart TB
    R["Request<br/>Authorization: Bearer …"]
    G1{"<b>Gate 1 — Authenticate</b><br/>valid JWT?"}
    G2["<b>Gate 2 — Scope</b><br/>BranchScopeMiddleware<br/>sets request.branch"]
    G3{"<b>Gate 3 — Permit</b><br/>'fees.collect' in<br/>effective permissions?"}
    G4["<b>Gate 4 — Filter</b><br/>get_queryset filters on branch<br/>perform_create stamps branch"]
    OK["200 / 201"]
    E1["401 Unauthorized"]
    E3["403 Forbidden"]
    E4["<b>404 Not Found</b>"]

    R --> G1
    G1 -->|no| E1
    G1 -->|yes| G2
    G2 --> G3
    G3 -->|no| E3
    G3 -->|yes| G4
    G4 -->|"row in scope"| OK
    G4 -->|"row in another branch"| E4

    classDef gate fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef good fill:#1f4a3a,stroke:#3fa37a,color:#fff
    classDef bad fill:#4a2a2a,stroke:#c46b6b,color:#fff
    class G1,G2,G3,G4 gate
    class OK good
    class E1,E3,E4 bad
```

**404, not 403, for a wrong-branch row** — a 403 confirms the object exists.
This is asserted by a test in every module (`04` §2).

## 5. Branch scope resolution

```mermaid
flowchart TB
    ST["Authenticated user"]
    Q1{"user.branch<br/>is NULL?"}
    HO["<b>Platform admin</b>"]
    Q2{"?branch=&lt;id&gt;<br/>supplied?"}
    ONE["scope = that one branch"]
    ALL["scope = ALL branches"]
    BU["<b>Branch user</b><br/>scope = user.branch<br/><i>?branch= is ignored, not rejected</i>"]
    Q3{"BranchAccess<br/>grants exist?<br/><i>V2</i>"}
    MULTI["scope = own branch + granted"]

    ST --> Q1
    Q1 -->|yes| HO --> Q2
    Q2 -->|yes| ONE
    Q2 -->|no| ALL
    Q1 -->|no| BU --> Q3
    Q3 -->|yes| MULTI
    Q3 -->|no| BU2["scope stays one branch"]

    classDef ho fill:#4a3a1f,stroke:#c9a227,color:#fff
    classDef bu fill:#1f4a3a,stroke:#3fa37a,color:#fff
    classDef v2 fill:#2a2a2a,stroke:#777,color:#aaa,stroke-dasharray:4 3
    class HO,ONE,ALL ho
    class BU,BU2 bu
    class Q3,MULTI v2
```

A copied platform-admin URL carrying `?branch=` therefore degrades safely in a
branch user's hands rather than erroring.

## 6. Permission resolution

Roles are **presets that tick boxes; the boxes are what is enforced.** An empty
list falls back to the preset, so accounts created before anyone customised
anything keep working (`02` §2).

```mermaid
flowchart TB
    U["User needs<br/><b>fees.collect</b>"]
    Q1{"user.permissions<br/>is empty?"}
    RP["Use <b>role preset</b><br/>Role.permission_matrix<br/>flattened to 'resource.action'"]
    UP["Use the user's own<br/><b>explicit list</b>"]
    Q2{"'fees.collect'<br/>present?"}
    SU{"is_superuser?"}
    Y["<b>Allow</b>"]
    N["<b>403</b>"]

    U --> SU
    SU -->|yes| Y
    SU -->|no| Q1
    Q1 -->|yes| RP --> Q2
    Q1 -->|no| UP --> Q2
    Q2 -->|yes| Y
    Q2 -->|no| N

    classDef good fill:#1f4a3a,stroke:#3fa37a,color:#fff
    classDef bad fill:#4a2a2a,stroke:#c46b6b,color:#fff
    classDef path fill:#1e3a5f,stroke:#4a90d9,color:#fff
    class Y good
    class N bad
    class RP,UP path
```

The catalogue of valid `resource.action` strings is served to the SPA from
`GET /api/accounts/permission-catalog/`, so the checkbox screen cannot drift
from what the backend enforces. One source of truth, not two copies.

## 7. Admission → enrolment

The conversion is **one transaction with three consequences**. All of it happens,
or none of it does.

```mermaid
flowchart TB
    A["<b>Application</b><br/>name, DOB, guardian, stream,<br/>class applied for"]
    B{"Screening /<br/>interview"}
    R["status = rejected"]
    C["status = accepted"]
    D["<b>ADMIT</b><br/>one click"]

    subgraph tx["single database transaction"]
        T1["Create <b>Student</b><br/>student_id = SIES-000123<br/><i>permanent, never reused</i>"]
        T2["Create <b>Enrolment</b><br/>class + section + session<br/>admission_no = ADM-DHK-2026-00417<br/>roll issued<br/><i>numbers under row lock</i>"]
        T3["Raise <b>Fee</b> invoices<br/>Admission Fee + Session Fee<br/>priced from the class"]
        T4["Link <b>Guardian</b><br/>new, or existing for a sibling"]
    end

    E["Student active<br/>appears on the class roster"]

    A --> B
    B -->|no| R
    B -->|yes| C --> D --> tx --> E

    classDef app fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef bad fill:#4a2a2a,stroke:#c46b6b,color:#fff
    classDef txn fill:#4a3a1f,stroke:#c9a227,color:#fff
    classDef done fill:#1f4a3a,stroke:#3fa37a,color:#fff
    class A,C app
    class R bad
    class T1,T2,T3,T4 txn
    class E done
```

Re-admission next session creates **a new Enrolment, never a new Student**. The
"admission history" the brief asks for is `student.enrolments.all()` — a query,
not a stored copy that drifts.

## 8. Fee lifecycle state machine

Status is **derived, never hand-set**. A field a human can set to "paid" without
money arriving is an invitation.

```mermaid
stateDiagram-v2
    [*] --> unpaid : invoice raised
    unpaid --> partial : payment &lt; payable
    unpaid --> paid : payment = payable
    unpaid --> overdue : due date passes
    partial --> partial : another part payment
    partial --> paid : balance cleared
    partial --> overdue : due date passes
    overdue --> overdue : nightly fine accrues<br/>capped by branch rule
    overdue --> partial : payment &lt; balance
    overdue --> paid : balance cleared
    unpaid --> waived : waived, with reason
    partial --> waived : remainder waived
    overdue --> waived : remainder waived
    paid --> partial : receipt reversed
    paid --> [*]
    waived --> [*]

    note right of paid
        paid_amount = sum of its Payments
        payable = amount - discount + fine
    end note
```

A wrong receipt is **reversed**, never deleted — deleting a paid invoice destroys
an accounting record (`01` §9).

## 9. Monthly fee generation (Celery)

Decision 2 of the "smart" list. Nobody clicks "raise this month's fees".

```mermaid
sequenceDiagram
    autonumber
    participant BEAT as celery-beat
    participant W as celery-worker
    participant DB as PostgreSQL

    BEAT->>W: 1st of month, 00:15<br/>generate_monthly_fees()
    loop for each active Branch
        W->>DB: active Enrolments for current Session
        loop for each enrolment
            W->>DB: monthly FeeCategories<br/>filtered by applies_to<br/>(hostel / transport flags)
            W->>W: amount = class monthly fee<br/>− student category discount
            W->>DB: INSERT Fee<br/>period = '2026-03'
            Note over DB: UNIQUE (branch, student,<br/>category, period, session)<br/><b>a second run writes nothing</b>
        end
    end
    W-->>BEAT: created N, skipped M
```

**Idempotency is enforced by the database, not by application code.** That
unique constraint is the single line standing between a retried job and a
double-charged guardian.

## 10. Fee collection at the counter

The most-used screen in the system, and the one cross-module write.

```mermaid
sequenceDiagram
    autonumber
    actor AC as Accountant
    participant UI as Collect Fee screen
    participant API as DRF
    participant DB as PostgreSQL

    AC->>UI: search by name / phone / admission no.
    UI->>API: GET /api/fees/?student=&status=unpaid,partial,overdue
    API-->>UI: outstanding invoices with balances
    AC->>UI: select invoice, enter amount + method + txn id
    UI->>API: POST /api/fees/{id}/collect/

    rect rgba(201,162,39,0.12)
        Note over API,DB: one transaction
        API->>DB: lock the receipt sequence for this branch
        API->>DB: INSERT Payment (receipt_no, amount, method, collected_by)
        API->>DB: UPDATE Fee.paid_amount, recompute status
        API->>DB: INSERT Income (category mapped from FeeCategory,<br/>source='fee_payment', payment=<id>)
    end

    API-->>UI: receipt payload
    UI-->>AC: print receipt
```

The **Income row is written by the system, not typed by a person.** That is why
the fee ledger and the accounts can never disagree — there is only one entry
(`05` §4.1).

## 11. Attendance month grid

Students down the side, thirty days across, marked cell by cell (`02` §4.4).

```mermaid
sequenceDiagram
    autonumber
    actor T as Teacher
    participant G as Register grid
    participant API as DRF
    participant DB as PostgreSQL

    T->>G: choose class, section, month
    G->>API: GET /api/attendance/register/?class=&section=&month=2026-03
    API->>DB: students in the enrolment + existing rows for the month
    API-->>G: days[] with is_markable, students[] with cells{}
    Note over G: off days and future dates<br/>render non-markable

    loop marking
        T->>G: P / A / L keys, arrows to move<br/>or "mark whole day present" on a column
        G->>G: track dirty cells only
    end

    T->>G: Save (or debounce fires)
    G->>API: POST /api/attendance/register/bulk/<br/>{cells: [dirty only]}

    rect rgba(63,163,122,0.12)
        Note over API,DB: one transaction
        API->>API: reject future dates and off days
        API->>DB: UPSERT on (branch, date, person_type, student)<br/>stamp taken_by = request.user
    end

    API-->>G: {saved, skipped[]}
```

1,800 cells cannot be 1,800 requests — hence the batch endpoint. The upsert key
is the table's existing unique constraint, so saving twice writes the same rows.

## 12. Examination → result

```mermaid
flowchart TB
    E1["<b>Exam</b> created<br/>session, stream, type"]
    E2["<b>ExamSchedule</b><br/>per subject: date, time,<br/>full marks, pass marks"]
    E3["<b>Marks entry</b><br/>teacher, one class × one subject<br/><i>permission: marks.enter</i>"]
    Q{"all subjects<br/>entered?"}
    E4["<b>PUBLISH</b><br/>principal only<br/><i>permission: exams.publish</i>"]

    subgraph job["Celery task"]
        C1["total and percentage<br/>per student"]
        C2["grade and grade point<br/>from the stream's scale"]
        C3["pass / fail<br/>+ failed subject list"]
        C4["rank in class<br/>and in section"]
    end

    E5["<b>Result</b> rows stored"]
    E6["Marksheet · tabulation sheet ·<br/>merit list · progress card"]
    E7["Visible to student<br/>via /api/me/"]

    E1 --> E2 --> E3 --> Q
    Q -->|no| E3
    Q -->|yes| E4 --> job --> E5 --> E6 & E7

    classDef setup fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef work fill:#4a1f3a,stroke:#c05299,color:#fff
    classDef done fill:#1f4a3a,stroke:#3fa37a,color:#fff
    class E1,E2,E3 setup
    class C1,C2,C3,C4 work
    class E5,E6,E7 done
```

Results are **stored, not computed on read**: a marksheet reprinted in three
years must show the same numbers even if the grade scale has since been edited.
*(In V1 the grade scale is simplified — see `05` §5.4.)*

## 13. Entity relationships (V1)

The twenty-nine-table cut line. `Enrolment` in the centre is the join that makes
history correct.

```mermaid
erDiagram
    BRANCH ||--o{ STREAM : "defines"
    BRANCH ||--o{ SESSION : "runs"
    BRANCH ||--o{ ACADEMIC_CLASS : "offers"
    BRANCH ||--o{ FORM_TEMPLATE : "seeds"
    STREAM ||--o{ STUDENT : "sector of"
    STREAM ||--o{ ACADEMIC_CLASS : "sector of"
    BRANCH ||--o{ STUDENT : "owns"
    BRANCH ||--o{ TEACHER : "employs"
    BRANCH ||--o{ FEE_CATEGORY : "seeds"
    BRANCH ||--o{ INCOME_CATEGORY : "seeds"
    BRANCH ||--o{ EXPENSE_CATEGORY : "seeds"
    BRANCH ||--o{ USER : "scopes"

    USER }o--o| ROLE : "preset"
    USER ||--o| STUDENT : "may log in as"
    USER ||--o| TEACHER : "logs in as"

    SESSION ||--o{ ACADEMIC_CLASS : "for"
    SESSION ||--o{ ENROLMENT : "for"
    ACADEMIC_CLASS ||--o{ SECTION : "split into"
    ACADEMIC_CLASS ||--o{ SUBJECT : "taught"
    ACADEMIC_CLASS ||--o{ ENROLMENT : "holds"
    SECTION ||--o{ ENROLMENT : "holds"

    STUDENT ||--o{ ENROLMENT : "year by year"
    STUDENT ||--o{ STUDENT_GUARDIAN : "has"
    GUARDIAN ||--o{ STUDENT_GUARDIAN : "of"
    STUDENT ||--o{ DOCUMENT : "files"
    ADMISSION }o--o| STUDENT : "becomes"

    ENROLMENT ||--o{ DAILY_ATTENDANCE : "day by day"
    ENROLMENT ||--o{ CLASS_ATTENDANCE : "period by period"
    ENROLMENT ||--o{ FEE : "billed"
    TEACHER ||--o{ DAILY_ATTENDANCE : "day by day"

    FEE_CATEGORY ||--o{ FEE : "kind of"
    FEE ||--o{ PAYMENT : "receipts"
    PAYMENT ||--o| INCOME : "auto-posts"
    INCOME_CATEGORY ||--o{ INCOME : "head"
    EXPENSE_CATEGORY ||--o{ EXPENSE : "head"

    EXAM ||--o{ EXAM_SCHEDULE : "papers"
    SUBJECT ||--o{ EXAM_SCHEDULE : "of"
    EXAM ||--o{ MARK : "scores"
    STUDENT ||--o{ MARK : "earns"
    SUBJECT ||--o{ MARK : "in"

    FORM_TEMPLATE ||--o{ QUESTION : "asks"
    ADMISSION ||--o{ ADMISSION_ANSWER : "answers"
    QUESTION ||--o{ ADMISSION_ANSWER : "answered by"
    ADMISSION ||--o{ PRINTED_FORM : "printed as"
    FORM_TEMPLATE ||--o{ PRINTED_FORM : "rendered from"
```

The three relationships that carry the design:

- `STUDENT ||--o{ ENROLMENT` — one person, many years.
- `FEE ||--o{ PAYMENT` — one invoice, many part payments.
- `PAYMENT ||--o| INCOME` — the money enters the accounts once, automatically.

## 14. Scheduled background jobs

Everything that happens without anyone clicking (`01` §4).

```mermaid
flowchart LR
    subgraph clock["celery-beat"]
        direction TB
        B1["<b>00:15</b>, 1st of month"]
        B2["<b>01:00</b> nightly"]
        B3["<b>02:00</b> nightly"]
        B4["<b>09:00</b> daily"]
        B5["<b>03:00</b> daily"]
    end

    B1 --> T1["generate monthly fee invoices<br/><i>idempotent on the unique key</i>"]
    B2 --> T2["accrue overdue fines<br/><i>capped by branch rule</i>"]
    B3 --> T3["report rollups<br/><i>V2</i>"]
    B4 --> T4["fee due / overdue SMS<br/><i>V2</i>"]
    B5 --> T5["database backup"]

    subgraph ondemand["on demand — queue: slow"]
        direction TB
        O1["publish results<br/>rank computation"]
        O2["PDF / Excel export<br/><i>V2</i>"]
        O3["bulk SMS / notices<br/><i>V2</i>"]
        O4["absence SMS on<br/>attendance submit <i>V2</i>"]
    end

    classDef v1 fill:#1f4a3a,stroke:#3fa37a,color:#fff
    classDef v2 fill:#2a2a2a,stroke:#777,color:#aaa,stroke-dasharray:4 3
    class T1,T2,T5,O1 v1
    class T3,T4,O2,O3,O4 v2
```

Two queues — `default` and `slow` — so one long export cannot starve fee
generation.

## 15. UI navigation map

Every sidebar entry is hidden unless `canView(resource)` passes, using the same
gate Awliaa's `DashboardLayout` already applies.

```mermaid
flowchart LR
    L["<b>Login</b><br/>11-digit phone<br/>+ password"] --> D["<b>Overview</b><br/>dashboard.view"]

    D --> N1["<b>Academics</b><br/>Classes · Sections<br/>Subjects · Sessions"]
    D --> N2["<b>Students</b><br/>All students · Admissions<br/>Enrolment · Documents"]
    D --> N3["<b>Staff</b><br/>Teachers · Employees<br/>Assignments"]
    D --> N4["<b>Attendance</b><br/><b>Month register</b> · Class attendance<br/>Daily register · Staff"]
    D --> N5["<b>Fees</b><br/><b>Collect fee</b> · Invoices<br/>Dues · Fee setup"]
    D --> N6["<b>Accounts</b><br/>Income · Expenses<br/>Ledger"]
    D --> N7["<b>Exams</b><br/>Exams · Schedule<br/><b>Marks entry</b> · Marksheets"]
    D --> N8["<b>Reports</b><br/>Students · Attendance<br/>Fees · Finance · Exams"]
    D --> N9["<b>Settings</b><br/>Branch · Fee categories"]
    D --> N10["<b>Users</b><br/>Accounts<br/>Roles and permissions"]
    D --> N11["<b>Branches</b><br/><i>the platform admin only</i>"]

    classDef hot fill:#4a3a1f,stroke:#c9a227,color:#fff
    classDef norm fill:#1e3a5f,stroke:#4a90d9,color:#fff
    classDef admin fill:#3a2a4a,stroke:#9b7fc4,color:#fff
    class N4,N5,N7 hot
    class N1,N2,N3,N6,N8 norm
    class N9,N10,N11 admin
```

Highlighted are the three screens where the institution's hours are actually
spent: **the attendance month register**, **collect fee**, and **marks entry**.
They share one interaction model — a keyboard-driven grid with batch save — so a
teacher who learns one knows all three.

---

## 16. The system in one sentence

> A branch-partitioned ledger of **people**, **time** and **money**, wrapped
> around one yearly loop, in which the recurring clerical work — raising fees,
> accruing fines, posting income — happens by itself.
