FROM node:22.18.0-alpine

RUN npm install --global firebase-tools@14.12.0 && \
    addgroup -S treta && adduser -S -G treta -u 10001 treta
WORKDIR /workspace
COPY firebase.json firestore.rules ./
USER 10001
EXPOSE 4000 8080 9099
CMD ["firebase", "emulators:start", "--project", "treta-local"]
