FROM circleci/node:14.3.0

# ARG HONEYBADGER_API_KEY

WORKDIR /home/circleci

COPY package.json .
COPY package-lock.json .

RUN npm install

COPY . .

CMD ["npm", "start"]
