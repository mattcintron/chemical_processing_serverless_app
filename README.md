
<div id="top"></div>

<br />

<h3 align="center">Chemical Processing Serverless API App</h3>

<p align="center">
  This repository contains the API code for a serverless proof-of-concept application focused on chemical data processing. It demonstrates how to:
  <ul>
    <li>Extract structured data from images of chemical labels using LLMs</li>
    <li>Analyze inventory datasets to identify entries containing chemical-related information</li>
  </ul>
  <strong>Explore the docs below »</strong>
</p>

---

## 📑 Table of Contents

<details>
  <summary>Expand</summary>
  <hr>
  <ol>
    <li><a href="#about-the-project">About the Project</a></li>
    <li><a href="#codebase-structure">Codebase Structure</a></li>
    <li><a href="#main-functionality">Main Functionality</a></li>
    <li><a href="#installation-and-usage">Installation and Usage</a></li>
    <li><a href="#deployment">Deployment</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>

---

## 🧪 About the Project

This project was built as a demonstration of how language models (LLMs) can be applied in scientific environments. It was developed for a proof-of-concept engagement with the company **SciShield**. All proprietary data and internal code have been excluded.

The application uses LLM agents orchestrated via an agnostic process to:
- Parse chemical label images into structured data
- Evaluate inventory datasets to identify chemical-related items

The system integrates with **AWS Bedrock**, and utilizes tools like **GPT** **Claude**, **AWS Lambda**, and **Zappa** to deliver a scalable and serverless API application.

---

## 📂 Codebase Structure

```bash
.
├── app.py                 # Main Flask app that launches the server
├── data/                  # Sample images and inventory datasets
├── integrations/
│   ├── routes.py          # Primary chemical image parsing endpoints
│   └── routes2.py         # Inventory analysis endpoints
├── hooks/                 # Git hooks (e.g., version bumping)
├── static/                # CSS and JavaScript files for UI
├── templates/             # Web templates (e.g., Swagger UI)
├── model_test_runs/      # Evaluation scripts for Claude and other models via AWS Bedrock
```

---

## ⚙️ Main Functionality

### 1. `app.py`
- Initializes the Flask application
- Hosts API endpoints and Swagger documentation UIs

### 2. `routes.py`
- 📍 **Swagger URL**: [`http://127.0.0.1:5000/chem-snap/docs`](http://127.0.0.1:5000/chem-snap/docs)
- Contains endpoints that:
  - Accept chemical label images
  - Use LLMs to extract structured chemical information
  - Return JSON-formatted output

### 3. `routes2.py`
- 📍 **Swagger URL**: [`http://127.0.0.1:5000/chemical_classification/docs`](http://127.0.0.1:5000/chemical_classification/docs)
- Accepts inventory data (in JSON format)
- Evaluates each row to determine:
  - Whether it describes a chemical entity
  - Additional metadata (e.g., CAS numbers, hazard info)

### 4. `model_test_runs/`
- Demonstrates:
  - How to invoke Claude and AWS-hosted models via Bedrock
  - Techniques for batch processing to avoid rate limits
  - Prompt engineering for transforming base models into task-specific agents
  - Generating reliable, formatted JSON output for downstream use

---

## 🚀 Installation and Usage

### 1. Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# Windows:
venv\Scripts\activate.bat
```

### 2. Install dependencies:

```bash
pip install -r requirements.txt
```

### 3. Run the Flask server locally:

```bash
python3 app.py
```

### 4. Zappa usage (for AWS deployment):

```bash
zappa init
zappa status dev
zappa update dev
```

---

## ☁️ Deployment

### Requirements
To fully deploy the application, ensure your AWS account has access to:
- **AWS Bedrock** (Claude, Amazon Titan, etc.)
- **AWS Secrets Manager**
- **Lambda and API Gateway**
- **Route 53** (for DNS management and custom domains)

### Deployment Process
- Deployment is automated using **GitHub Actions (GHA)** and **Zappa**
- `zappa_settings.json` defines the configuration
- Before GHA will work, the app must first be deployed locally via:
  
  ```bash
  zappa deploy dev
  ```

- Once deployed:
  - GitHub Actions can trigger `zappa update`
  - Lambda and Route 53 manage hosting and DNS
  - Optional: Configure AWS custom domain support

> **Note**: The `.github/workflows/` directory contains CI/CD automation scripts. These are commented out to prevent accidental execution without proper AWS credentials.

---

## 🛣️ Roadmap

- [ ] Add support for additional chemical classification models
- [ ] Containerize for local Docker-based testing

---

## 📜 License

This repository is intended as an example for educational and POC demonstration purposes only. Please contact the repository maintainer for reuse or licensing information.

---
