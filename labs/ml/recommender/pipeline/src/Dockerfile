# Image for the recommender pipeline components, built for the host architecture by install --with-ml; build context is labs/ml/recommender
FROM python:3.13-slim

WORKDIR /usr/local/src/kfp/components
COPY pipeline/src/runtime-requirements.txt runtime-requirements.txt
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r runtime-requirements.txt

RUN pip install --no-cache-dir kfp==2.18.0
COPY recommender/ recommender/
COPY pipeline/src/ .
ENV PYTHONPATH=/usr/local/src/kfp/components
