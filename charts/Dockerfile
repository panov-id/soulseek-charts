FROM golang:1.25-alpine AS build
WORKDIR /source
COPY go.mod ./
COPY *.go ./
# Statically linked so the binary runs on the host without any runtime.
ENV CGO_ENABLED=0
RUN go mod tidy && go build -ldflags="-s -w" -o /soulseek-charts .

FROM scratch
COPY --from=build /soulseek-charts /soulseek-charts
ENTRYPOINT ["/soulseek-charts"]
