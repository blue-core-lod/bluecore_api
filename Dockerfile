FROM cimg/node:16.8

ENV HONEYBADGER_API_KEY
ENV HONEYBADGER_ENV

WORKDIR /home/circleci

COPY --chown=circleci:circleci package.json .
COPY --chown=circleci:circleci package-lock.json .

RUN npm install

COPY --chown=circleci:circleci . .

ENV NODE_ENV production

CMD ["npm", "start"]
