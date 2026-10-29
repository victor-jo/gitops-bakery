# gitops-bakery

**명령 한 번으로 노트북에 GitOps 실험실을 굽고, 그다음은 Claude Code에게 말로 시킨다.**

[English](README.md)

```bash
npx github:victor-jo/gitops-bakery#v0.1.1 install
```

11분쯤 지나면 kind 클러스터 위에 아래 구성요소가 서로 연결된 채로 떠 있다.

- GitLab과 GitLab Runner
- Harbor
- Argo CD (App of Apps)
- Prometheus와 Grafana

Claude Code에는 이 실험실용 스킬과 MCP 서버가 등록된다. 그다음 이렇게 말하면 된다.

> "FastAPI 앱 하나 만들어서 GitOps로 배포해 줘."

Claude가 GitLab 저장소, CI 파이프라인, Argo CD Application을 만든다. 파이프라인은 테스트, rootless BuildKit 빌드, Harbor push, 매니페스트 태그 갱신 순서로 돈다. 1분 반쯤 뒤에는 앱이 응답하는 URL을 돌려준다.

## 왜 만들었나

도구마다 튜토리얼은 넘친다. 그런데 이어 붙이는 순간 막힌다.

- 레지스트리를 누가 어떤 이름으로 부르는가
- docker 데몬도 없는 CI 파드에서 이미지를 어떻게 굽는가
- 새 버전이 왜 3분 뒤에야 뜨는가

이 프로젝트는 그 스택을 손으로 쌓다가 만난 [함정 9개](docs/traps.md)에서 시작했다. 설치기가 그 함정을 전부 미리 막아 둔다. 디버깅 대신 바로 실험을 시작하면 된다.

## 필요한 것

| | |
|---|---|
| 기기 | Apple Silicon macOS (v0.1은 이 환경에서만 검증했다) |
| Docker | 메모리 **10 GiB 이상**의 [OrbStack](https://orbstack.dev). Docker Desktop은 동작할 수도 있는 수준 |
| `PATH`의 CLI | `kind`, `helm`, `kubectl`, `git`, Node.js 20 이상 |
| 127.0.0.1의 빈 포트 | 80, 30001, 30002, 30004, 30010–30019 |
| 선택 | 스킬과 MCP를 쓰려면 [Claude Code](https://claude.com/claude-code)(`claude`) |
| `--with-ml`을 쓸 때 | Docker 메모리 **14 GiB 이상**, `sudo cloud-provider-kind`로 실행 중인 [cloud-provider-kind](https://github.com/kubernetes-sigs/cloud-provider-kind) |

설치 전에 점검부터 해 볼 수 있다.

```bash
npx github:victor-jo/gitops-bakery#v0.1.1 doctor
```

## 설치되는 것

| 구성요소 | 주소 | 사용자 |
|---|---|---|
| GitLab CE 19.5 | http://localhost | `root` |
| Harbor 2.15 | http://localhost:30001 | `admin` |
| Argo CD 3.5 | http://localhost:30002 | `admin` |
| Grafana | http://localhost:30004 | `admin` |
| 내가 만든 앱 | http://localhost:30010 – 30019 | |

- **비밀번호**는 설치할 때 무작위로 만들어 `~/.gitops-bakery/secrets.json`(권한 600)에 저장한다. 위치는 `gitops-bakery credentials`로 확인한다.
- **클러스터 이름**은 docker 컨테이너처럼 무작위로 붙는다. `airy-scone`, `golden-danish` 같은 식이다.
- **내부 구성은 이렇다.**
  - kind 노드 4대(컨트롤 플레인 1, 워커 3)
  - GitLab용 DB, Redis, S3로 CloudNativePG(PostgreSQL 17), Valkey, Garage
  - Kubernetes executor와 rootless BuildKit을 쓰는 GitLab Runner
  - GitLab 저장소 `devops/platform`(모니터링)과 `devops/service`(앱)를 바라보는 Argo CD root Application 두 개

손으로 apply하는 건 root 두 개뿐이다. 모니터링 설정 변경을 포함해 나머지는 전부 git을 거친다.

## 써 보기

Claude Code 새 세션에서 이렇게 말해 본다.

```
hello라는 FastAPI 앱을 만들어서 GitOps로 배포해 줘.
```

```
hello 상태 보여 줘. 파이프라인이랑 이미지 태그도.
```

```
hello의 루트 엔드포인트가 현재 시각도 돌려주게 고쳐서 push하고, 새 버전이 뜨면 알려 줘.
```

http://localhost:30004 의 Grafana 홈 대시보드에는 앱별 요청 수가 쌓인다.

## ML 실습 (선택)

```bash
brew install cloud-provider-kind
sudo cloud-provider-kind            # 다른 터미널에 켜 둔다
npx github:victor-jo/gitops-bakery install --with-ml
```

기본 실험실 위에 MLflow, JupyterLab, Feast, Kubeflow Pipelines 2.18이 올라간다. 올라가는 길도 같다. 전부 `devops/platform`의 Argo CD Application이다. 화면마다 포트 대신 이름이 붙는다.

| 화면 | 이름 |
|---|---|
| MLflow, JupyterLab | `mlflow.<ip>.sslip.io`, `jupyter.<ip>.sslip.io` |
| Feast 온라인 서버 | `feast.<ip>.sslip.io` |
| KFP | `kfp.<ip>.sslip.io` |
| Grafana | `grafana.<ip>.sslip.io` (NodePort도 그대로 둔다) |

`<ip>`는 cloud-provider-kind가 그 네임스페이스에 준 gateway 주소를 점 대신 대시로 적은 것이다. 설치기가 이 주소를 읽어 이름을 만들고 커밋한다. 만들어진 이름은 `status`로 확인한다.

설치기는 Garage 버킷과 키, Secret도 만든다. 그 다음 클러스터 안 Job이 일을 이어받는다.
- 예제 데이터와 Feast 레지스트리 두 개를 넣는다.
- 온라인 저장소에 사용자 30,162명을 채운다.

그래서 준비 단계에서 Mac에 Python이 필요 없다. 파이프라인 이미지도 지금 아키텍처로 빌드해 Harbor에 올린다.

남은 실습은 [labs/ml](labs/ml/README.md)에 있다. 모델 학습, `champion` 모델 고르기, 파이프라인 실행이다. 이 옵션은 state에 기록된다. 그래서 다음에 옵션 없이 `install`을 돌려도 ML 층은 유지된다. 이미 있는 실험실이라면 `install --with-ml`을 한 번 돌리면 된다.

## MCP 도구

| 도구 | 하는 일 |
|---|---|
| `bakery_status` | 네임스페이스별 파드 상태, URL, 사용자 이름, 클러스터 안 레지스트리 이름, 앱 목록, 비밀번호 파일 위치 |
| `bakery_create_app` | GitLab `apps/<name>`과 `apps/<name>-manifests`, raw CI 변수, FastAPI 템플릿, 30010–30019 중 포트 하나, Argo CD Application |
| `bakery_app_status` | 최근 파이프라인과 job, Harbor 태그, Argo CD 동기화와 상태, URL |
| `bakery_delete_app` | Application, 저장소 두 개, Harbor 저장소 삭제 |

도구 응답에는 비밀번호나 토큰이 절대 들어가지 않는다. 자세한 내용은 [docs/mcp-tools.md](docs/mcp-tools.md)에 있다.

## 명령

```
gitops-bakery install [--force] [--with-ml]   # 실험실 생성 또는 이어서 진행 (다시 실행해도 안전)
gitops-bakery status              # 파드 상태와 URL
gitops-bakery credentials         # 사용자 이름과 비밀번호 파일 위치
gitops-bakery doctor              # 사전 점검만
gitops-bakery uninstall [--yes]   # 클러스터, MCP 등록, 스킬, ~/.gitops-bakery 삭제
gitops-bakery mcp                 # stdio MCP 서버 (Claude Code가 실행)
```

`bakery`는 짧은 별칭이다.

## 측정값 (M 시리즈 MacBook, OrbStack)

| | |
|---|---|
| 처음 설치 | 676초 |
| `bakery_create_app` → 앱 응답 | 92초 |
| 소스 push → 새 버전 반영 | 45–72초 |
| CI 태그 커밋 → 새 버전 반영 | 4–13초 |
| 노드 4대 메모리 합계 | 약 7.8 GiB (`--with-ml`이면 약 11.6 GiB) |

태그 커밋 뒤 반영이 빠른 건 CI가 push 직후 Argo CD에 새로고침을 직접 요청하기 때문이다. GitLab webhook으로는 안 된다. webhook에는 `http://localhost/...` 주소가 실리는데, Argo CD가 지켜보는 저장소 주소는 클러스터 안 주소라 서로 맞지 않는다. 자세한 내용은 [docs/architecture.md](docs/architecture.md)에 있다.

## 업그레이드

새 태그로 `install`을 다시 실행하면 된다(예: `npx github:victor-jo/gitops-bakery#v0.1.1 install`). 이미 끝난 단계는 건너뛰고 새 단계만 돈다. Claude Code의 MCP 등록과 스킬도 새 버전에 맞춰 다시 고정된다.

## 삭제

```bash
npx github:victor-jo/gitops-bakery#v0.1.1 uninstall
```

`--with-ml`로 설치했다면 삭제 뒤 `sudo cloud-provider-kind`를 껐다 다시 켠다. 클러스터가 지워져도 cloud-provider-kind는 그 클러스터 LoadBalancer의 80번 포트를 계속 잡고 있다. 그대로 두면 다음 설치에서 GitLab이 80번 포트를 쓰지 못한다.

## 로드맵

- KServe로 `champion` 모델 서빙, "학습 → 서빙" 템플릿
- ML 이름 전부를 gateway 하나(IP 하나)로 받기
- Codex, Cursor, Gemini CLI 연동
- Linux(amd64) 지원과 CI에서 도는 E2E 테스트
- npm 배포

## 라이선스

[Apache-2.0](LICENSE). AGPL-3.0인 Garage는 저장소에 포함하지 않고, 설치할 때 받아 온다.
