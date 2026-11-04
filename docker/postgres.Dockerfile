# Build the official gosu 1.20 source with the patched moby/sys/user dependency.
# Both inputs are pinned: the builder image by digest and gosu by upstream commit.
FROM --platform=$BUILDPLATFORM golang:1.24.6-alpine@sha256:c8c5f95d64aa79b6547f3b626eb84b16a7ce18a139e3e9ca19a8c078b85ba80d AS gosu-builder

ARG TARGETARCH
ARG GOSU_COMMIT=29b939aa5bd4dc588af765b8248f6e39150d2565

RUN apk add --no-cache git
RUN git init /src \
    && git -C /src remote add origin https://github.com/tianon/gosu.git \
    && git -C /src fetch --depth=1 origin "$GOSU_COMMIT" \
    && git -C /src checkout --detach FETCH_HEAD

WORKDIR /src
RUN grep -q 'github.com/moby/sys/user v0.4.1' go.mod
RUN go install golang.org/x/vuln/cmd/govulncheck@v1.1.4 \
    && /go/bin/govulncheck ./...
RUN mkdir -p /out \
    && CGO_ENABLED=0 GOOS=linux GOARCH="$TARGETARCH" \
    go build -mod=readonly -trimpath -buildvcs=false -o /out/gosu .
RUN /go/bin/govulncheck -mode=binary /out/gosu

FROM postgres:16-alpine
COPY --from=gosu-builder /out/gosu /usr/local/bin/gosu
RUN gosu --version && gosu nobody true
