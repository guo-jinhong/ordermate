FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /workspace

COPY pom.xml .
RUN mvn -B -q -DskipTests dependency:go-offline

COPY src ./src
RUN mvn -B -q -DskipTests package

FROM eclipse-temurin:17-jre-jammy
WORKDIR /app
COPY --from=build /workspace/target/ecommerce-order-system-1.0.0.jar app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
