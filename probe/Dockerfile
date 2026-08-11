FROM golang:1.23-alpine AS build
WORKDIR /source
COPY go.mod main.go ./
RUN go build -o /soulseek-probe .

FROM alpine:3.20
COPY --from=build /soulseek-probe /usr/local/bin/soulseek-probe
ENTRYPOINT ["soulseek-probe"]
