# doctor-docker 🩺🐳

**doctor-docker** is a friendly, dependency-free CLI tool that diagnoses common Docker and Docker Compose problems before they waste your time.

It helps answer the painful question:

> “Why is my Docker project not starting?”

Instead of reading confusing logs for 30 minutes, run one command:

```bash
python doctor_docker.py
````

And get a clear report like this:

```txt
🩺 doctor-docker
Project: /home/user/my-app

Project score: 62/100

1. ❌ Docker daemon is not reachable
   Problem: Cannot connect to the Docker daemon.
   Fix: Start Docker Desktop or run: sudo systemctl start docker

2. ❌ Compose references missing env_file(s)
   Problem: Missing: .env
   Fix: Copy .env.example to .env and fill the values.

3. ⚠️ .dockerignore is missing
   Problem: Docker may send unnecessary files into the build context.
   Fix: Create .dockerignore with .git, node_modules, .env, dist, build.
```

---

## Why doctor-docker exists

Docker errors are often simple, but the error messages can be confusing.

Common problems include:

* Docker is installed but not running
* Docker Compose is missing
* `compose.yaml` has invalid YAML
* `.env` file is missing
* Required env variables are missing
* A port like `3000`, `5432`, or `8000` is already in use
* Containers exit instantly
* Logs contain hidden dependency errors
* Dockerfile uses risky or incomplete settings
* `.dockerignore` is missing
* Wrong CPU architecture image is used
* Permission issues happen on Linux

**doctor-docker** checks these problems and explains them in human language.

---

## Features

### System checks

doctor-docker checks:

* Docker CLI availability
* Docker daemon status
* Docker Compose plugin availability
* Legacy `docker-compose` detection
* Operating system information
* Python version information

### Project checks

doctor-docker scans your project for:

* `compose.yaml`
* `compose.yml`
* `docker-compose.yaml`
* `docker-compose.yml`
* `Dockerfile`
* `.dockerignore`
* `.env`
* `.env.example`

### Compose checks

doctor-docker can detect:

* Missing Compose file
* Invalid Compose configuration
* Suspicious YAML indentation
* Tab characters inside YAML
* Missing top-level `services:` key
* Missing `env_file` files
* Unnecessary old `version:` key
* Busy host ports

### Dockerfile checks

doctor-docker can detect:

* Empty Dockerfile
* Missing `FROM`
* Risky implicit `latest` image usage
* Missing `.dockerignore`
* Possible large build context problems

### Log analysis

If containers exist, doctor-docker analyzes recent Compose logs for common problems:

* Port conflicts
* Permission errors
* Missing files
* Missing modules
* Database connection errors
* Authentication errors
* CPU/platform mismatch
* Out-of-memory errors
* YAML errors
* Node package errors
* Python dependency errors

---

## Installation

No package installation is required.

You only need:

* Python 3.8+
* Docker, if you want Docker-specific checks
* Docker Compose, if your project uses Compose

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/doctor-docker.git
cd doctor-docker
```

Run:

```bash
python doctor_docker.py
```

---

## Usage

### Check current folder

```bash
python doctor_docker.py
```

### Check another project folder

```bash
python doctor_docker.py /path/to/project
```

Example:

```bash
python doctor_docker.py ~/projects/my-docker-app
```

### Analyze more log lines

```bash
python doctor_docker.py --logs 200
```

### Skip log analysis

```bash
python doctor_docker.py --no-logs
```

---

## Example output

```txt
🩺 doctor-docker
Project: /home/user/project
System: Linux 6.8.0 | Python 3.12.3

Project score: 76/100

1. ✅ Docker CLI is installed
   - Docker version 27.0.3, build abc123

2. ✅ Docker daemon is running
   - Server version: 27.0.3

3. ✅ Docker Compose plugin is available
   - Docker Compose version v2.28.1

4. ✅ Compose file found
   - compose.yaml

5. ❌ Compose references missing env_file(s)
   Problem: Missing: .env
   Fix: Create the missing file(s). If you have .env.example, copy it to .env.

6. ❌ One or more Compose host ports are already in use
   Problem: 8000
   Fix: Stop the process using the port, or change the left side of the port mapping.

Summary:
Errors: 2 | Warnings: 0 | Total checks/findings: 6
Result: Problems found. Fix the ERROR items first.
```

---

## Testing with the broken example

This repository includes an intentionally broken Docker Compose project:

```txt
examples/broken-compose/
```

Run doctor-docker against it:

```bash
python doctor_docker.py examples/broken-compose
```

You should see problems such as:

* Missing `.env`
* Missing `.dockerignore`
* Possible port conflict
* Dockerfile warnings
* Container/runtime issues if you run the Compose project

To start the broken example:

```bash
cd examples/broken-compose
docker compose up
```

Then in another terminal:

```bash
python ../../doctor_docker.py .
```

---

## Example broken Compose project

The example project intentionally contains mistakes.

It is not supposed to be perfect.

It exists so you can test whether doctor-docker detects common issues.

Current intentional problems:

* `compose.yaml` references `.env`, but `.env` is missing
* `.env.example` exists, but `.env` does not
* `.dockerignore` is missing
* Port `8000` may conflict with another local app
* Dockerfile uses `python:latest`, which is risky
* App depends on an environment variable
* App can fail if required env values are missing

---

## How scoring works

doctor-docker gives your project a score from `0` to `100`.

The score is not a security guarantee.

It is a quick health estimate.

General meaning:

| Score  | Meaning                  |
| ------ | ------------------------ |
| 85-100 | Looks healthy            |
| 60-84  | Usable, but has warnings |
| 0-59   | Needs fixes              |

Errors reduce the score more than warnings.

---

## Exit codes

doctor-docker uses exit codes so it can be used in scripts or CI.

| Exit code | Meaning                 |
| --------- | ----------------------- |
| 0         | No major problems found |
| 1         | Warnings found          |
| 2         | Errors found            |

Example:

```bash
python doctor_docker.py
echo $?
```

---

## Use in CI

You can add doctor-docker to a GitHub Actions workflow.

Example:

```yaml
name: Docker Doctor

on:
  pull_request:
  push:

jobs:
  doctor-docker:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Run doctor-docker
        run: python doctor_docker.py --no-logs
```

Note:

In CI, Docker may not always be running unless you configure it.
For basic file checks, `--no-logs` is recommended.

---

## Supported platforms

doctor-docker is designed to run on:

* Linux
* macOS
* Windows

It uses only the Python standard library.

No external Python packages are required.

---

## Requirements

Minimum:

```txt
Python 3.8+
```

Optional:

```txt
Docker CLI
Docker Compose plugin
```

doctor-docker will still run if Docker is missing.
It will simply report that Docker is not installed or not available.

---

## Project philosophy

doctor-docker follows 4 rules:

1. **Do not crash**
2. **Explain the problem clearly**
3. **Suggest a practical fix**
4. **Avoid dangerous automatic changes**

This tool does not automatically delete containers, kill processes, or edit your files.

It only diagnoses and explains.

---

## What doctor-docker does not do

doctor-docker does not:

* Replace Docker documentation
* Fix your project automatically
* Guarantee production readiness
* Detect every possible Docker issue
* Upload logs anywhere
* Modify your files without permission

It is a local diagnostic helper.

---

## Roadmap

Planned features:

* `--json` output
* Automatic README badge
* Better Dockerfile best-practice checks
* Better Node.js detection
* Better Python dependency detection
* GitHub Actions template generator
* Optional auto-fix mode
* More log patterns
* Better Windows process detection
* Project type detection: Node, Python, Go, PHP, Java

---

## Possible future commands

```bash
doctor-docker scan
doctor-docker logs
doctor-docker ports
doctor-docker env
doctor-docker doctor --json
doctor-docker fix --dry-run
```

---

## Safety

doctor-docker is read-only by default.

It does not:

* Kill processes
* Remove containers
* Delete images
* Delete volumes
* Edit Compose files
* Edit environment files
* Send data to a server

Everything runs locally on your machine.

---

## Contributing

Contributions are welcome.

Good first issues:

* Add new log patterns
* Improve Windows support
* Improve Dockerfile checks
* Add JSON output
* Add tests
* Improve README examples
* Add screenshots

Fork the repo, create a branch, and open a pull request.

```bash
git checkout -b feature/my-improvement
```

---

## Development

Run locally:

```bash
python doctor_docker.py
```

Run against the broken example:

```bash
python doctor_docker.py examples/broken-compose
```

Run without logs:

```bash
python doctor_docker.py examples/broken-compose --no-logs
```

---

## Suggested repository topics

Add these topics to your GitHub repo:

```txt
docker
docker-compose
cli
python
developer-tools
devops
debugging
diagnostics
troubleshooting
containers
```

---

## License

MIT License.

You are free to use, modify, and distribute this project.

---

## Author

Created by **YOUR_NAME**.

If this tool saved your time, consider giving the repository a star ⭐.
