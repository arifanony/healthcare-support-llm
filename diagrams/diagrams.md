# Diagrams

Version-controlled Mermaid sources. Render in any Mermaid-compatible viewer
(GitHub, VS Code extensions, mermaid.live).

## 1. System architecture

```mermaid
flowchart TB
    Human([Human<br/>final authority]) -->|approve / correct / reject| Review[T6 Human Review]
    Human -->|approve golden lock| GoldenLock[data/golden<br/>GOLDEN_LOCK]
    Human -->|accept / reject results| Report[Comparison Report]

    Raw[(data/raw<br/>immutable)] --> T3[T3 Structuring]
    T3 --> Proc[(data/processed)]
    Proc --> T4[T4 Atomic Extraction]
    T4 --> T5[T5 Auto Triage<br/>ACCEPT/REVIEW/REJECT]
    T5 --> Review
    Review --> Cur[(data/curated)]
    Review --> Neg[(data/negative)]
    Cur --> T8[T8 Quality Checks]
    T8 -->|go| T9[T9 Split]
    T8 -->|no-go| Review
    T9 --> Splits[(data/splits<br/>train / validation)]
    T9 --> GoldenLock

    Splits --> Job[Training Job Spec<br/>+ human approval]
    Job --> GPU[[GPU Backend<br/>Colab - remote executor]]
    GPU --> Art[Adapter + Metrics + Logs]
    Art --> Exp[(experiments/ run record)]

    GoldenLock --> EvalA[T11a Baseline Eval<br/>base model]
    EvalA --> BaseRes[(Baseline Results<br/>locked)]
    Art --> EvalB[T11b Comparison Eval<br/>fine-tuned]
    EvalB --> Report
    BaseRes --> Report
    Report --> T12[T12 Error Analysis]
    T12 -->|approved iteration| T8
    T12 -->|closed| Done([Project Complete])

    Genesis[Genesis State Layer<br/>stages + gates] -.->|tracks| T3
    Genesis -.->|tracks| T9
    Genesis -.->|tracks| Job
    Genesis -.->|tracks| Report
```

## 5a. Local development environment

```mermaid
flowchart LR
    Dev([Developer]) <--> VSCode[VS Code]
    VSCode <--> Agent[Coding Agent<br/>edits + local runs]
    Agent <--> Repo[(Local Repository<br/>src / configs / docs / data)]
    Repo --> Scripts[Scripts + Checks<br/>hash, split, leak-check]
    Repo --> ExpRec[experiments/<br/>run records]
    Human2([Human Reviewer]) -->|T6 queue<br/>T9 lock, T11 accept| Repo
```

## 5b. Local ↔ remote GPU execution

```mermaid
sequenceDiagram
    participant Local as Local Repo (Genesis/Agent)
    participant Human as Human
    participant Colab as Colab GPU Backend
    participant Store as Artifact Store

    Local->>Human: job spec for approval
    Human-->>Local: approved
    Local->>Colab: upload spec + train/val jsonl + script pin
    Colab->>Colab: provision runtime, install pinned deps
    Colab->>Colab: train (checkpoint every N steps)
    alt session lost
        Colab->>Local: partial artifacts + failure note
        Local->>Colab: relaunch with resumed_from
    end
    Colab->>Local: adapter + tokenizer + metrics.json + logs
    Local->>Store: artifacts/<run-id>/ (hash-verified)
    Local->>Local: experiments/<run-id>/ record
```

## 2. Data lifecycle

```mermaid
flowchart LR
    R[Raw<br/>write-once] --> P[Processed<br/>normalized + atomic]
    P --> Q{Quality?<br/>triage + human}
    Q -->|approved| C[Curated]
    Q -->|rejected| N[Negative<br/>with reason]
    C --> S{Split<br/>grouped, seeded}
    S --> T[Train 80%]
    S --> V[Validation 10%]
    S --> G[Golden 10%<br/>locked]
    T --> M[Training]
    V --> M
    M --> E[Evaluation]
    G --> E
    N -.->|future| PT[Preference Tuning]
    E --> A[Error Analysis]
    A -.->|iteration| Q
```

## 3. Human review flow (T6)

```mermaid
flowchart TB
    Q[Review Queue<br/>REVIEW first, ACCEPT sample, REJECT audit] --> Pick[Reviewer picks record]
    Pick --> Insp[Inspect: source conversation,<br/>atomic example, triage verdict,<br/>quality reasons, proposed action]
    Insp --> Dec{Decision}
    Dec -->|ACCEPT| App[human_approved<br/>+ reviewer + timestamp]
    Dec -->|EDIT| Corr[human_corrected<br/>original preserved in history]
    Dec -->|REJECT| Rej[human_rejected<br/>+ negative reason code]
    App --> Next{Queue empty?}
    Corr --> Next
    Rej --> Next
    Next -->|no| Pick
    Next -->|yes| T7[T7: build curated + negative stores]
```

## 4. Model training / evaluation flow

```mermaid
flowchart LR
    Base[Base SLM] --> E1[T11a Baseline Eval<br/>golden, frozen harness]
    E1 --> BL[(Baseline Results<br/>locked)]
    Base --> FT[T10 LoRA/QLoRA SFT<br/>curated train, val early-stop]
    FT --> Ad[Adapter + Metrics + Logs]
    Ad --> E2[T11b Comparison Eval<br/>identical golden + harness]
    E2 --> CR[Comparison Report<br/>aggregates + slices + safety census]
    BL --> CR
    CR --> H{Human accept?}
    H -->|yes| T12[T12 Error Analysis]
    H -->|no| Diag[Diagnose: data / training / eval]
    Diag -.->|iteration| FT
```

## 6. Genesis state / workflow flow

```mermaid
flowchart TB
    D[Discovery] --> S[SPEC.md draft]
    S --> SC[genesis spec check]
    SC -->|pass| SA{Human approves spec?}
    SC -->|fail| S
    SA -->|no| S
    SA -->|yes| P[Planning: bounded tasks + gates]
    P --> PC[genesis plan check]
    PC -->|pass| PA{Human approves plan?}
    PC -->|fail| P
    PA -->|no| P
    PA -->|yes| I[Implement active task only]
    I --> G{Mandatory gates pass?}
    G -->|no| I
    G -->|yes| R{Risk ≥ medium?}
    R -->|yes| IR[Independent review<br/>maker cannot self-approve]
    R -->|no| C[genesis task complete]
    IR --> C
    C --> N{More tasks?}
    N -->|yes| I
    N -->|no| Done([Phase complete])
```

## 7. Provenance flow

```mermaid
flowchart LR
    Raw[data/raw<br/>SHA-256 manifest] -->|T3| Conv[conversation/v1<br/>conversation_id]
    Conv -->|T4| At[atomic/v1<br/>example_id + parent_ids]
    At -->|T5| Tr[+ triage verdict<br/>model + prompt version]
    Tr -->|T6| Rv[+ review decision<br/>reviewer + timestamp]
    Rv -->|T7| Cu[curated / negative<br/>store manifest]
    Cu -->|T9| Sp[train / val / golden<br/>split manifest + seed]
    Sp -->|T10| Run[adapter + run record<br/>job spec + hashes]
    Run -->|T11| Ev[eval report<br/>golden lock hash]
    Ev -.->|audit| Raw
```
