FROM golang:1.25-alpine AS build
WORKDIR /source
COPY go.mod ./
COPY *.go ./
# Static build so the same binary also runs directly on the host.
ENV CGO_ENABLED=0
RUN go mod tidy && go build -ldflags="-s -w" -o /soulseek-resolve .

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
COPY --from=build /soulseek-resolve /usr/local/bin/soulseek-resolve
ENTRYPOINT ["soulseek-resolve"]
