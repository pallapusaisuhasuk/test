from flask import Flask, render_template, request, jsonify
from rdflib import Graph, Namespace, RDF, RDFS, Literal
from pathlib import Path
import re
import requests

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
RDF_FILE = BASE_DIR / "TourismKG_Final_Fixed(2).rdf"
KG = Graph()
KG.parse(str(RDF_FILE), format="xml")
NS = Namespace("https://example.org/tourismkg/2026#")
KG.bind("tourismkg", NS)

def local_name(uri):
    return str(uri).rsplit("#", 1)[-1].rsplit("/", 1)[-1]

def display_name(uri):
    value = next(KG.objects(uri, NS.displayName), None)
    return str(value) if value is not None else local_name(uri).replace("_", " ")

# Build a searchable index from actual displayName values and RDF individual names.
ENTITY_INDEX = {}
for subject in set(KG.subjects()):
    if str(subject).startswith(str(NS)):
        label = display_name(subject)
        ENTITY_INDEX[label.casefold()] = subject
        ENTITY_INDEX[local_name(subject).replace("_", " ").casefold()] = subject

def find_entity(text, required_type=None):
    low = text.casefold()
    matches = sorted(ENTITY_INDEX.items(), key=lambda item: len(item[0]), reverse=True)
    for label, uri in matches:
        if label and re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", low):
            if required_type is None or (uri, RDF.type, NS[required_type]) in KG:
                return uri
    return None

def qname(uri):
    return "tourismkg:" + local_name(uri)

def make_query(question):
    q = question.strip()
    low = q.casefold()
    if not q:
        raise ValueError("Please enter a question.")

    # Find a known city/country/attraction in the supplied RDF.
    city = find_entity(q, "City")
    country = find_entity(q, "Country")
    attraction = find_entity(q, "TouristAttraction")

    # 1. Attractions in a city
    if any(k in low for k in ["attraction", "tourist place", "places to visit", "sites in", "things to see"]) and city:
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?attractionName
WHERE {{
  ?attraction a tourismkg:TouristAttraction ;
              tourismkg:locatedInCity {qname(city)} ;
              tourismkg:displayName ?attractionName .
}}
ORDER BY ?attractionName"""
        return sparql, "attractions_in_city", {"city": display_name(city)}

    # 2. Which cities are in a country?
    if city is None and country and any(k in low for k in ["cities", "city", "located in", "in the country", "in country"]):
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?cityName
WHERE {{
  ?city a tourismkg:City ;
        tourismkg:cityInCountry {qname(country)} ;
        tourismkg:displayName ?cityName .
}}
ORDER BY ?cityName"""
        return sparql, "cities_in_country", {"country": display_name(country)}

    # 3. Country of a city
    if city and any(k in low for k in ["which country", "what country", "country is", "belongs to", "city in which country"]):
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?countryName
WHERE {{
  {qname(city)} tourismkg:cityInCountry ?country .
  ?country tourismkg:displayName ?countryName .
}}"""
        return sparql, "country_of_city", {"city": display_name(city)}

    # 4. Attraction type/category
    if attraction and any(k in low for k in ["type", "category", "museum or", "what kind", "classified"]):
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?typeName
WHERE {{
  {qname(attraction)} a ?type .
  FILTER(?type IN (tourismkg:Museum, tourismkg:HistoricSite, tourismkg:ReligiousSite, tourismkg:Monument))
  BIND(REPLACE(STR(?type), "^.*#", "") AS ?typeName)
}}"""
        return sparql, "attraction_type", {"attraction": display_name(attraction)}

    # 5. All instances of an attraction class
    class_map = [
        (["museums", "museum"], "Museum", "museum"),
        (["historic sites", "historical sites", "historic places"], "HistoricSite", "historic_site"),
        (["religious sites", "temples", "religious places"], "ReligiousSite", "religious_site"),
        (["tourist attractions", "tourist attraction", "attractions"], "TouristAttraction", "tourist_attractions"),
    ]
    for words, cls, intent in class_map:
        if any(w in low for w in words) and not city and not attraction:
            sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?name
WHERE {{
  ?item a tourismkg:{cls} ;
        tourismkg:displayName ?name .
}}
ORDER BY ?name"""
            return sparql, intent, {}

    # 6. Rail routes between cities / services departing from a city
    if any(k in low for k in ["train", "rail", "railway", "route", "travel from", "services from"]):
        if city:
            sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?serviceName ?destinationName
WHERE {{
  ?service a tourismkg:RailService ;
           tourismkg:serviceOriginCity {qname(city)} ;
           tourismkg:serviceDestinationCity ?destination ;
           tourismkg:displayName ?serviceName .
  ?destination tourismkg:displayName ?destinationName .
}}
ORDER BY ?serviceName"""
            return sparql, "rail_from_city", {"city": display_name(city)}
        # Explicitly named origin and destination
        cities = [u for label, u in sorted(ENTITY_INDEX.items(), key=lambda x: len(x[0]), reverse=True)
                  if (u, RDF.type, NS.City) in KG and re.search(r"(?<!\w)"+re.escape(label)+r"(?!\w)", low)]
        unique = list(dict.fromkeys(cities))
        if len(unique) >= 2:
            origin, destination = unique[0], unique[1]
            sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?serviceName
WHERE {{
  ?service a tourismkg:RailService ;
           tourismkg:serviceOriginCity {qname(origin)} ;
           tourismkg:serviceDestinationCity {qname(destination)} ;
           tourismkg:displayName ?serviceName .
}}"""
            return sparql, "rail_between_cities", {"origin": display_name(origin), "destination": display_name(destination)}

    # 7. Accessibility details for a named attraction
    if attraction and any(k in low for k in ["accessible", "accessibility", "step free", "wheelchair"]):
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?details
WHERE {{
  {qname(attraction)} tourismkg:hasAccessibilityFeature ?feature .
  ?feature tourismkg:accessibilityDetails ?details .
}}"""
        return sparql, "accessibility", {"attraction": display_name(attraction)}

    # 8. Free admission
    if attraction and any(k in low for k in ["free", "admission", "ticket", "entry"]):
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?free
WHERE {{
  {qname(attraction)} tourismkg:hasAdmissionTicket ?ticket .
  ?ticket tourismkg:isFreeAdmission ?free .
}}"""
        return sparql, "free_admission", {"attraction": display_name(attraction)}

    # 9. Generic list all countries or cities
    if "countries" in low or "all countries" in low:
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?name WHERE {{ ?x a tourismkg:Country ; tourismkg:displayName ?name . }} ORDER BY ?name"""
        return sparql, "all_countries", {}
    if "cities" in low or "all cities" in low:
        sparql = f"""PREFIX tourismkg: <{NS}>
SELECT DISTINCT ?name WHERE {{ ?x a tourismkg:City ; tourismkg:displayName ?name . }} ORDER BY ?name"""
        return sparql, "all_cities", {}

    raise ValueError(
        "I couldn't map that question to a supported pattern in this RDF file. Try one of the example questions below. "
        "The current knowledge graph contains cities, countries, tourist attractions, attraction types, rail services, "
        "accessibility information and admission information."
    )

def run_query_local(sparql):
    result = KG.query(sparql)
    columns = [str(v) for v in result.vars]
    rows = [[str(value) if value is not None else "" for value in row] for row in result]
    return columns, rows

def run_query_fuseki(sparql, endpoint):
    # Fuseki query endpoint, for example http://localhost:3030/tourism/sparql
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("Fuseki endpoint must start with http:// or https://.")
    try:
        response = requests.post(
            endpoint,
            data={"query": sparql},
            headers={"Accept": "application/sparql-results+json"},
            timeout=20
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            "Could not connect to Fuseki. Check that Fuseki is running, the dataset name is correct, "
            "and the SPARQL endpoint URL is correct. Details: " + str(exc)
        )
    try:
        payload = response.json()
        variables = payload.get("head", {}).get("vars", [])
        bindings = payload.get("results", {}).get("bindings", [])
        rows = [[binding.get(var, {}).get("value", "") for var in variables] for binding in bindings]
        return variables, rows
    except (ValueError, AttributeError, TypeError) as exc:
        raise RuntimeError("Fuseki returned an unexpected response. Make sure you entered the query endpoint, not the dataset URL.") from exc

@app.route("/")
def home():
    return render_template("index.html", triple_count=len(KG))

@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json(silent=True) or {}
    question = data.get("question", "")
    backend = data.get("backend", "fuseki")
    endpoint = data.get("endpoint", "http://localhost:3030/tourism/sparql").strip()
    try:
        sparql, intent, entities = make_query(question)
        if backend == "fuseki":
            columns, rows = run_query_fuseki(sparql, endpoint)
            source = "Apache Jena Fuseki"
        else:
            columns, rows = run_query_local(sparql)
            source = "Local RDFLib"
        return jsonify({
            "ok": True, "question": question, "intent": intent,
            "entities": entities, "sparql": sparql,
            "columns": columns, "rows": rows, "count": len(rows),
            "source": source
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
