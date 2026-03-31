FROM alpine:3.20
RUN apk add --no-cache wireguard-tools iproute2 iputils-ping
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
