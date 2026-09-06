#!/bin/bash
# Scale gather: real GitHub API metadata across Kanak's project domains.
# qualifiers in-query (stars, pushed, archived); license post-filtered.
set -u
OUT=/tmp/repo_scale; rm -rf "$OUT"; mkdir -p "$OUT"
J='fullName,url,description,stargazersCount,pushedAt,license,language,forksCount,isArchived'
PUSHED="pushed:>2025-04-01"; ARCH="archived:false"

# tag|query-core  (each run in two star tiers to catch famous + active-smaller)
Q=(
"exopipe|exoplanet detection transit"
"exopipe|light curve TESS kepler"
"exopipe|astronomy photometry pipeline"
"exopipe|astrophysics time series"
"smart_traffic|traffic simulation"
"smart_traffic|road network analysis"
"smart_traffic|intelligent transportation system"
"smart_traffic|SUMO traffic modeling"
"roadpipe|road segmentation deep learning"
"roadpipe|satellite road extraction"
"GPUForge|GPU training orchestration"
"GPUForge|distributed training machine learning"
"GPUForge|ml infrastructure scheduler"
"GPUForge|model training pipeline kubernetes"
"PyraSec|static analysis security scanner"
"PyraSec|SAST security tool"
"PyraSec|secret detection scanning"
"PyraSec|SBOM software bill of materials"
"PyraSec|vulnerability scanner"
"PyraSec|threat modeling STRIDE"
"vyomnetra|satellite orbit tracking sgp4"
"vyomnetra|space situational awareness"
"vyomnetra|orbital mechanics simulation"
"vyomnetra|astrodynamics python"
"klions|programming language compiler"
"klions|interpreter language implementation"
"klions|systems programming language rust"
"klions|parser lexer language"
"klions|virtual machine bytecode"
"irvision|satellite imagery deep learning"
"irvision|remote sensing segmentation"
"irvision|super resolution imagery"
"irvision|geospatial machine learning"
"ERA-AI|local llm desktop app"
"ERA-AI|ollama gui client"
"ERA-AI|offline ai assistant"
"ERA-AI|llm chat interface local"
"ERA-AI|private local language model"
"LiveTalk|speech translation realtime"
"LiveTalk|whisper transcription translation"
"LiveTalk|voice translation app"
"LiveTalk|real time speech to text"
"vidyut/prabha|vscode extension"
"vidyut/prabha|code visualization editor"
"vidyut/prabha|c graphics library retro"
"vidyut/prabha|debugger visualization"
"medha-ide|python ide code editor"
"medha-ide|desktop code editor"
"medha-ide|monaco editor app"
"StadiumSaathi|streamlit application"
"StadiumSaathi|streamlit dashboard llm"
"fasal-kavach|agriculture ai advisory"
"fasal-kavach|crop disease detection"
"fasal-kavach|climate early warning"
"fasal-kavach|precision agriculture ml"
"HealthForecastAI|hospital readmission prediction"
"HealthForecastAI|healthcare machine learning"
"HealthForecastAI|clinical risk prediction"
"HealthForecastAI|patient outcome model"
"product-intelligence|product catalog enrichment"
"product-intelligence|data enrichment llm pipeline"
"luminix|medical image classification"
"luminix|deep learning diagnosis cnn"
"gimp-llm-editor|ai image editing"
"gimp-llm-editor|image generation editing tool"
"gimp-llm-editor|computer vision image processing"
)

i=0
for e in "${Q[@]}"; do
  tag="${e%%|*}"; q="${e#*|}"
  for tier in "stars:>=200" "stars:25..199"; do
    i=$((i+1)); f="$OUT/$(printf '%03d' $i).json"
    gh search repos "$q $tier $PUSHED $ARCH" --limit 60 --sort stars --json "$J" >"$f" 2>/tmp/gse_$i \
      && python3 -c "import json;d=json.load(open('$f'));[x.update(_tag='$tag') for x in d];json.dump(d,open('$f','w'))" \
      && printf '.' \
      || printf 'x'
    sleep 1.2
  done
done
echo
echo "raw total: $(python3 -c "import json,glob;print(sum(len(json.load(open(f))) for f in glob.glob('$OUT/*.json')))")"
echo "=== SCALE GATHER DONE ==="
