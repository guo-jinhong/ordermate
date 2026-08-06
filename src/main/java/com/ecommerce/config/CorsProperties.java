package com.ecommerce.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

@Data
@Component
@ConfigurationProperties(prefix = "cors")
public class CorsProperties {
    private List<String> allowedOrigins = new ArrayList<>();
    private String allowedMethods = "GET,POST,PUT,DELETE,OPTIONS";
    private String allowedHeaders = "Authorization,Content-Type,X-Requested-With";
    private boolean allowCredentials = true;
    private long maxAge = 3600;

    public List<String> getAllowedMethodList() {
        return Arrays.asList(allowedMethods.split(","));
    }

    public List<String> getAllowedHeaderList() {
        return Arrays.asList(allowedHeaders.split(","));
    }
}
