# Tourism NLP to SPARQL application (Fuseki + RDFLib)

This Flask application turns supported natural-language questions into SPARQL and executes them against either:
- **Apache Jena Fuseki** (default; recommended for the Semantic Data Technologies project)
- **Local RDFLib** (fallback for testing without Fuseki)

## 1. Start Apache Jena Fuseki

1. Start Apache Jena Fuseki on your Mac.
2. Open `http://localhost:3030`.
3. Create a dataset named `tourism` (choose a persistent or in-memory dataset).
4. Open the dataset's **upload** page and upload `TourismKG_Final_Fixed(2).rdf`.
5. Confirm the dataset is available at `http://localhost:3030/#/dataset/tourism`.
6. The query endpoint should be:

   `http://localhost:3030/tourism/sparql`

If you created a dataset with a different name, change the endpoint in the web app. For example, dataset `travelkg` uses `http://localhost:3030/travelkg/sparql`.

## 2. Run the Flask application

Open Terminal in this project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## 3. Use the application

1. Leave **Query execution** set to **Apache Jena Fuseki**.
2. Check the endpoint field. Default: `http://localhost:3030/tourism/sparql`.
3. Enter a natural-language question or choose an example.
4. Click **Generate SPARQL & Run Query**.
5. The page displays the generated SPARQL and the answer rows returned by Fuseki.

Choose **Local RDFLib (offline)** to execute against the RDF file bundled with the application instead.

## Example questions

- Which cities are located in Italy?
- Which tourist attractions are located in London?
- Which attractions are museums?
- What type of attraction is the Colosseum?
- Which trains depart from Cambridge?
- Is the British Museum accessible?
- Is admission to the British Museum free?
- Which country is Cambridge in?

## How it works

1. RDFLib reads the RDF/XML file to build an entity index for the lightweight NLP layer.
2. The rule-based NLP layer identifies supported question patterns and entities.
3. The app generates a SPARQL SELECT query.
4. In Fuseki mode, Flask sends that SPARQL query to the Fuseki HTTP query endpoint using an HTTP POST request.
5. Fuseki evaluates the query against the dataset and returns SPARQL Results JSON.
6. The HTML page renders the returned columns and rows.

**Important:** This is a rule-based NLP demonstration, not a general-purpose language model. Add more question patterns in `make_query()` in `app.py` to support additional competency questions from your ontology.
