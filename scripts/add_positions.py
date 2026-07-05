"""Script puntual para añadir posiciones a players_to_analyze.json. Borrar tras usar."""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

POSITIONS = {
    # ── Real Madrid ──────────────────────────────────────────────
    "kylian-mbappe": "DC", "vinicius-junior": "EI", "rodrygo": "ED",
    "franco-mastantuono": "MC", "gonzalo-garcia": "MCO", "jude-bellingham": "MCO",
    "federico-valverde": "MC", "arda-gler": "MCO", "brahim-diaz": "EI",
    "eduardo-camavinga": "MC", "aurelien-tchouameni": "MCD", "dani-ceballos": "MC",
    "thiago-pitarch": "MC", "manuel-ngel": "MC", "cesar-palacios": "MC",
    "jorge-cestero": "DFC", "trent-alexander-arnold": "LD", "antonio-rudiger": "DFC",
    "dean-huijsen": "DFC", "der-milito": "DFC", "daniel-carvajal": "LD",
    "raul-asencio-1": "DFC", "david-alaba": "DFC", "lvaro-fernandez-1": "LT",
    "ferland-mendy": "LT", "fran-garcia": "LT", "manuel-serrano": "MCD",
    "thibaut-courtois": "POR", "andriy-lunin": "POR", "fran-gonzalez-2": "POR",
    "alvaro-gonzalez-1": "POR",
    # ── FC Barcelona ─────────────────────────────────────────────
    "robert-lewandowski": "DC", "marcus-rashford": "EI", "ferran-torres": "EI",
    "roony-bardghji": "ED", "lamine-yamal": "ED", "raphinha": "ED",
    "pedri-gonzalez": "MC", "pablo-gavi": "MC", "frenkie-de-jong": "MC",
    "fermin-lopez": "MCO", "dani-olmo": "MCO", "marc-bernal": "MCD",
    "marc-casado": "MCD", "pau-cubarsi": "DFC", "jules-kounde": "LD",
    "alejandro-balde": "LT", "ronald-araujo": "DFC", "joao-cancelo": "LD",
    "andreas-christensen": "DFC", "eric-garcia": "DFC", "gerard-martin": "LT",
    "xavi-espart": "DFC", "joan-garcia": "POR", "wojciech-szczesny": "POR",
    # ── Atlético Madrid ──────────────────────────────────────────
    "julian-lvarez": "DC", "antoine-griezmann": "MCO", "ademola-lookman": "ED",
    "alexander-sorloth": "DC", "thiago-almada": "MCO", "giuliano-simeone": "EI",
    "nicolas-gonzalez": "MC", "lex-baena": "EI", "johnny-cardoso": "MCD",
    "pablo-barrios": "MC", "koke-resurreccion": "MC", "obed-vargas": "MC",
    "rodrigo-mendoza": "MC", "rayane-belaid": "EI", "iker-luque": "DC",
    "javi-morcillo": "EI", "nahuel-molina": "LD", "marcos-llorente": "MC",
    "clement-lenglet": "DFC", "robin-le-normand": "DFC", "jose-maria-gimenez": "DFC",
    "david-hancko": "DFC", "marc-pubill": "LD", "matteo-ruggeri": "LT",
    "javier-bonar": "DFC", "juan-musso": "POR", "jan-oblak": "POR",
    "salvi-esquivel": "EI",
    # ── Athletic Club ─────────────────────────────────────────────
    "maroan-sannadi": "DC", "gorka-guruzeta": "DC", "urko-izeta": "DC",
    "nico-williams": "EI", "inaki-williams": "EI", "oihan-sancet": "MCO",
    "alex-berenguer": "EI", "mikel-jauregizar": "ED", "inigo-ruiz-de-galarreta": "MC",
    "robert-navarro": "MCD", "unai-gomez": "MC", "alejandro-rego": "EI",
    "benat-prados": "MC", "selton-sanchez": "MC", "mikel-vesga": "MCD",
    "nico-serrano": "DFC", "aymeric-laporte": "DFC", "dani-vivian": "DFC",
    "adama-boiro": "LD", "yuri-berchiche": "LT", "aitor-paredes": "DFC",
    "yeray-alvarez": "DFC", "jesus-areso": "LD", "andoni-gorosabel": "LD",
    "inigo-lekue": "LD", "unai-egiluz": "LT", "unai-simon": "POR",
    "alex-padilla": "POR",
    # ── Real Sociedad ─────────────────────────────────────────────
    "mikel-oyarzabal": "EI", "orri-steinn-skarsson": "DC", "jon-karrikaburu": "DC",
    "takefusa-kubo": "ED", "wesley-gassova": "EI", "luka-sucic": "MCO",
    "arsen-zakharyan": "EI", "goncalo-guedes": "ED", "yangel-herrera": "MC",
    "carlos-soler": "MC", "ander-barrenetxea": "EI", "brais-mendez": "MCO",
    "benat-turrientes": "MC", "jon-gorrotxategi": "LD", "pablo-marin": "MC",
    "jon-aramburu": "LD", "sergio-gomez": "LT", "duje-caleta-car": "DFC",
    "alvaro-odriozola": "LD", "jon-martin": "DFC", "igor-zubeldia": "DFC",
    "aihen-munoz": "LT", "aritz-elustondo": "DFC", "alex-remiro": "POR",
    "unai-marrero": "POR",
    # ── Real Betis ────────────────────────────────────────────────
    "cedric-bakambu": "DC", "cucho-hernandez": "DC", "ezequiel-avila": "DC",
    "antony": "ED", "abde-ezzalzouli": "EI", "sofyan-amrabat": "MCD",
    "isco-alarcon": "MCO", "giovani-lo-celso": "MCO", "lvaro-fidalgo": "MC",
    "nelson-deossa": "MC", "rodrigo-riquelme": "EI", "pablo-fornals": "MCO",
    "pablo-garcia-1": "MC", "marc-roca": "MCD", "sergi-altimira": "MC",
    "hector-bellerin": "LD", "natan": "DFC", "junior-firpo": "LT",
    "ricardo-rodriguez": "LT", "marc-bartra": "DFC", "diego-javier-llorente": "DFC",
    "aitor-ruibal": "LD", "ngel-ortiz": "MCD", "pablo-busto": "DFC",
    "adriansan-miguel": "POR", "pau-lopez": "POR", "alvaro-valles": "POR",
    # ── Villarreal ────────────────────────────────────────────────
    "georges-mikautadze": "DC", "nicolas-pepe": "ED", "gerard-moreno": "DC",
    "ayoze-perez": "EI", "tani-oluwaseyi": "ED", "alfonso-gonzalez": "EI",
    "hugo-lopez": "MCO", "thomas-teye": "MC", "pape-gueye": "MCD",
    "tajon-buchanan": "EI", "alberto-moleiro": "MCO", "dani-parejo": "MC",
    "alassane-diatta": "ED", "santi-comesana": "MC", "renato-veiga": "DFC",
    "juan-foyth": "LD", "santiago-mourino": "DFC", "willy-kambwala": "DFC",
    "rafa-marin": "DFC", "sergi-cardona": "LT", "alex-freeman": "EI",
    "logan-costa": "DFC", "alfonso-pedraza": "LT", "pau-navarro": "DFC",
    "arnau-tenas": "POR", "luiz-junior": "POR", "diego-conde": "POR",
    # ── Valencia ──────────────────────────────────────────────────
    "lucas-beltran": "DC", "arnaut-danjuma": "EI", "umar-sadiq": "DC",
    "hugo-duro": "DC", "largie-ramazani": "EI", "daniel-raba": "EI",
    "guido-rodriguez": "MCD", "javi-guerra-1": "MCO", "pepelu": "MC",
    "diego-lopez-1": "MC", "andre-almeida-1": "ED", "luis-rioja": "EI",
    "filip-ugrinic": "MC", "baptiste-santamaria": "MCD", "lucas-nunez": "MC",
    "mouctar-diakhaby": "DFC", "jose-gaya": "LT", "-renzo-saravia": "LD",
    "cesar-tarrega": "DFC", "thierry-correia": "LD", "unai-nunez": "DFC",
    "eray-cmert": "DFC", "dimitri-foulquier": "LD", "jesus-vazquez-1": "LT",
    "jose-manuel-copete": "LT", "marcos-navarro-1": "DFC", "rubi-munoz": "MC",
    "julen-agirrezabala": "POR", "stole-dimitrievski": "POR", "cristian-rivero": "POR",
    # ── Sevilla ───────────────────────────────────────────────────
    "alexis-sanchez": "DC", "akor-adams": "DC", "chidera-ejuke": "EI",
    "neal-maupay": "DC", "isaac-romero": "DC", "ruben-vargas": "EI",
    "djibril-sow": "MC", "lucien-agoume": "MC", "nemanja-gudelj": "MCD",
    "adnan-januzaj": "EI", "batista-mendy": "MCD", "juanlu-sanchez": "LD",
    "peque": "ED", "joan-jordan": "MC", "joaquin-oso": "DC",
    "manu-bueno": "DFC", "cesar-azpilicueta": "LD", "gabriel-suazo": "LT",
    "tanguy-kouassi": "MCD", "marcao": "DFC", "jose-ngel-carmona": "DFC",
    "kike-salas": "DFC", "federico-gattoni": "DFC", "fabio-cardoso": "DFC",
    "andres-castrin": "LD", "iker-munoz-1": "LT", "odysseas-vlachodimos": "POR",
    "rjan-nyland": "POR",
    # ── Celta Vigo ────────────────────────────────────────────────
    "borja-iglesias": "DC", "iago-aspas": "EI", "ferran-jutgla": "DC",
    "jones-el-abdellaoui": "ED", "pablo-duran": "MCO", "ilaix-moriba": "MC",
    "williot-swedberg": "EI", "scar-mingueza": "LD", "matias-vecino": "MC",
    "fer-lopez": "EI", "franco-cervi": "EI", "hugo-lvarez-": "MC",
    "hugo-sotelo": "MCD", "sergio-carreira": "LD", "javi-rueda": "LD",
    "miguel-roman": "MC", "marcos-alonso": "LT", "joseph-aidoo": "DFC",
    "carl-starfelt": "DFC", "javi-rodriguez": "LT", "mihailo-risti": "LD",
    "lvaro-nunez": "DFC", "yoel-lago": "POR", "carlos-dominguez": "POR",
    "manu-fernandez-1": "POR", "andrei-radu": "POR", "ivan-villar": "POR",
    "marc-vidal": "POR",
    # ── Osasuna ───────────────────────────────────────────────────
    "victor-munoz": "ED", "ante-budimir": "DC", "raul-garcia-1": "MCO",
    "kike-barja": "EI", "iker-benito": "MC", "raul-moro": "EI",
    "aimar-oroz": "MCO", "ruben-garcia": "EI", "jon-moncayola": "MC",
    "lucas-torro": "MCD", "moi-gomez": "EI", "iker-munoz": "MC",
    "boyomo": "DFC", "javi-galan": "LT", "alejandro-catena": "DFC",
    "valentin-rosier": "LD", "abel-bretones": "DFC", "jorge-herrando": "DFC",
    "juan-cruz-1": "LT", "asier-osambela": "MC", "sergio-herrera": "POR",
    "aitor-fernandez": "POR",
    # ── Getafe ────────────────────────────────────────────────────
    "martin-satriano": "DC", "borja-mayoral": "DC", "luis-vazquez": "DC",
    "veljko-birmancevic": "ED", "adrian-liso": "EI", "juanmi-jimenez": "EI",
    "lex-sancris": "MCD", "mario-martin": "MC", "luis-milla": "MCO",
    "mauro-arambarri": "MCD", "abu-kamara": "EI", "javi-munoz": "MC",
    "adrian-riquelme": "MC", "abdel-abqar": "MCD", "dakonam-djene": "DFC",
    "sebastian-boselli": "DFC", "zaid-romero": "DFC", "ismael-bekhoucha": "EI",
    "diego-rico": "LT", "allan-nyom": "LD", "domingos-duarte": "DFC",
    "juan-iglesias": "DFC", "davinchi": "ED", "kiko-femenia": "LD",
    "david-soria": "POR", "jiri-letacek": "POR",
    # ── Rayo Vallecano ────────────────────────────────────────────
    "alemo": "DC", "jorge-de-frutos": "ED", "carlos-martin": "EI",
    "sergio-camello": "DC", "randy-nteka": "MCO", "ilias-akhomach": "EI",
    "pathe-ciss": "MCD", "isi-palazon": "EI", "alvaro-garcia": "EI",
    "pedro-diaz": "MC", "unai-lopez": "MCO", "oscar-trejo": "MCO",
    "scar-valentin": "MC", "fran-perez": "EI", "gerard-gumbau": "MCD",
    "andrei-florin": "DFC", "nobel-mendy": "LD", "abdul-mumin": "DFC",
    "florian-lejeune": "DFC", "luiz-felipe": "DFC", "alfonso-espino": "LT",
    "ivan-balliu": "LD", "pep-chavarria": "LD", "jozhua-vertrouwd": "DFC",
    "augusto-batalla": "POR", "dani-cardenas": "POR", "adrian-molina": "POR",
    # ── Mallorca ──────────────────────────────────────────────────
    "vedat-muriqi": "DC", "zito-luvumbo-1": "EI", "takuma-asano": "ED",
    "mateo-joseph": "DC", "abdon-prats": "DC", "pablo-torre": "MCO",
    "jan-virgili": "MC", "samu-almeida": "MCO", "sergi-darder": "MC",
    "omar-mascarell": "MCD", "manuel-morlanes": "MC", "jastin-kalumba": "MCD",
    "antonio-sanchez": "MC", "javi-llabres": "ED", "jan-salas": "LT",
    "johan-mojica": "LT", "pablo-maffeo": "LD", "marash-kumbulla": "DFC",
    "martin-valjent": "DFC", "antonio-raillo": "DFC", "mateu-morey": "LD",
    "antonio-lato": "LT", "david-lopez-1": "DFC", "javier-olaizola": "LD",
    "luis-orejuela": "LD", "lucas-bergstrom": "POR", "leo-roman": "POR",
    "ivan-cuellar": "POR",
    # ── Girona ────────────────────────────────────────────────────
    "vladyslav-vanat": "DC", "cristhian-stuani": "DC", "abel-ruiz": "DC",
    "cristian-portu": "ED", "claudio-echeverri": "MCO", "azzedine-ounahi": "MC",
    "axel-witsel": "MCD", "donny-van-de-beek": "MC", "thomas-lemar": "EI",
    "viktor-tsygankov": "ED", "bryan-gil": "EI", "lass-kourouma": "MC",
    "ivan-martin": "MCO", "fran-beltran": "MCD", "joel-roca": "MCD",
    "ricard-artero": "LD", "vitor-reis": "DFC", "daley-blind": "DFC",
    "arnau-martinez": "LD", "alex-moreno": "LT", "alejandro-frances": "DFC",
    "david-lopez": "DFC", "hugo-rincon": "DFC", "marc-andre-ter-stegen": "POR",
    "paulo-gazzaniga": "POR", "vladyslav-krapyvtsov": "POR", "ruben-blanco": "POR",
    "juan-carlos-martin": "DFC",
    # ── Espanyol ──────────────────────────────────────────────────
    "roberto-fernandez-1": "EI", "cyril-ngonge": "EI", "kike-garcia": "DC",
    "lluc-castell": "DC", "charles-pickel": "MCD", "javi-puado": "EI",
    "edu-exposito": "MCO", "pere-milla": "ED", "tyrhys-dolan": "EI",
    "pol-lozano": "ED", "terrats": "MC", "urko-gonzalez-de-zarate": "MC",
    "jofre-carreras": "LD", "antoniu-roca": "DFC", "miguel-londono": "DFC",
    "omar-el-hilali": "DFC", "carlos-romero": "DFC", "leandro-cabrera": "DFC",
    "clemens-riedel": "DFC", "fernando-calero": "DFC", "jose-salinas": "LT",
    "miguel-ngel-rubio": "LD", "adama-timera": "LT", "marko-dmitrovic": "POR",
    "ngel-fortuno": "POR", "pol-tristan": "POR",
    # ── Deportivo Alavés ──────────────────────────────────────────
    "mariano-diaz": "DC", "ibrahim-diabate": "DC", "antonio-martinez": "DC",
    "lucas-boye": "DC", "aitor-manas": "ED", "abde-rebbach": "EI",
    "antonio-blanco": "MCD", "carles-alena": "MCO", "denis-suarez": "MCO",
    "calebe": "MC", "carlos-benavidez": "MC", "pablo-ibanez": "DFC",
    "jon-guridi": "MCD", "ander-guevara": "MCD", "angel-perez-1": "MC",
    "youssef-enriquez": "MC", "facundo-garces": "DFC", "nahuel-tenaglia": "LD",
    "jonny-castro": "LD", "jon-pacheco": "LT", "ville-koski": "LT",
    "victor-parada": "DFC", "antonio-sivera": "POR", "raul-fernandez": "POR",
    # ── Real Oviedo ───────────────────────────────────────────────
    "federico-vinas": "EI", "thiago-borbas": "DC", "alex-fores": "ED",
    "haissem-hassan": "EI", "santi-cazorla": "MCO", "kwasi-sibo": "MC",
    "ilyas-chaira": "EI", "leander-dendoncker": "MCD", "thiago-fernandez": "MC",
    "luka-ilic": "MCO", "nicolas-fonseca": "MCD", "santiago-colombatto": "MCD",
    "alberto-reina": "MC", "ovie-ejaria": "MCO", "brandon-domingues": "EI",
    "pablo-agudin": "DFC", "eric-bertrand-bailly": "DFC", "rahim-alhassane": "DFC",
    "david-carmo": "DFC", "javi-lopez-1": "LD", "nacho-vidal": "LD",
    "david-costas": "DFC", "dani-calvo": "DFC", "lucas-ahijado": "LT",
    "horatiu-moldovan": "POR", "aaron-escandell": "POR",
    # ── Elche ─────────────────────────────────────────────────────
    "alvaro-rodriguez": "EI", "andre-silva": "DC", "rafa-mir": "DC",
    "adam-boayar": "ED", "tete-morente": "EI", "alex-sanchez-2": "ED",
    "lucas-cepeda": "EI", "federico-redondo": "MC", "grady-diangana": "EI",
    "aleix-febas": "MCO", "gonzalo-villar": "MC", "german-valera": "LD",
    "martim-neto": "MCD", "marc-aguado": "DFC", "yago-santiago": "LD",
    "josan": "ED", "hector-fort": "LD", "david-affengruber": "DFC",
    "buba-sangare": "DFC", "adria-pedrosa": "LT", "victor-chust": "DFC",
    "pedro-bigas": "DFC", "leo-petrot": "DFC", "john-nwankwo": "DFC",
    "inaki-pena": "POR", "matias-dituro": "POR",
    # ── Levante UD ────────────────────────────────────────────────
    "etta-eyong": "DC", "carlos-espi": "EI", "jose-luis-morales": "EI",
    "ivan-romero": "DC", "tai-abed": "MC", "paco-cortes": "MC",
    "kervin-arriaga": "MC", "carlos-alvarez": "MC", "oriol-rey": "DFC",
    "iker-losada": "MC", "ugo-raghouber": "DC", "kareem-tunde": "EI",
    "pablo-martinez": "LD", "jon-ander-olasagasti": "MC", "unai-vencedor": "MCD",
    "victor-garcia-1": "LD", "roger-brugue": "DFC", "matias-moreno": "DFC",
    "alan-matturro": "DFC", "manu-sanchez": "LT", "adrian-de-la-fuente": "EI",
    "jeremy-toljan": "LD", "unai-elgezabal": "DFC", "diego-pampin": "DFC",
    "mat-ryan": "POR", "pablo-campos": "POR", "alejandro-primo": "POR",
}


def main():
    with open(DATA / "players_to_analyze.json", encoding="utf-8") as f:
        data = json.load(f)

    assigned = 0
    missing = []
    for team in data["teams"]:
        for player in team["players"]:
            slug = player["name"]
            if slug in POSITIONS:
                player["position"] = POSITIONS[slug]
                assigned += 1
            else:
                missing.append(slug)

    with open(DATA / "players_to_analyze.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ {assigned} jugadores con posición asignada.")
    if missing:
        print(f"⚠️  Sin posición ({len(missing)}): {', '.join(missing)}")


if __name__ == "__main__":
    main()
