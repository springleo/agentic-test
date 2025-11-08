# Demo Spring Boot app — add two integers

This repository contains a tiny Spring Boot application that exposes a single endpoint to add two integers.

Endpoints

- GET /add?a=1&b=2  — returns JSON with a, b and sum.

Build & run locally (with Java 17 and Maven installed)

```bash
mvn -B package
java -jar target/demo-0.0.1-SNAPSHOT.jar
# then open http://localhost:8080/add?a=3&b=5
```

Run tests

```bash
mvn -B test
```

Docker

Build the docker image (requires Docker installed):

```bash
docker build -t demo-add:latest .
docker run -p 8080:8080 demo-add:latest
# then curl http://localhost:8080/add?a=2&b=2
```

CI

The repository includes a GitHub Actions workflow at `.github/workflows/ci.yml` that runs `mvn test` and `mvn package` on push and pull requests.
# agentic-test