package com.ecommerce.security;

import com.ecommerce.dto.ApiResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class RegisterRateLimitFilter extends OncePerRequestFilter {

    private static final int MAX_ATTEMPTS = 5;
    private static final long WINDOW_MS = 3_600_000;

    private static final ConcurrentMap<String, RateLimitEntry> cache = new ConcurrentHashMap<>();

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        String method = request.getMethod();
        return !("POST".equalsIgnoreCase(method) && path.endsWith("/users/register"));
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String ip = getClientIp(request);
        String key = "register:" + ip;

        RateLimitEntry entry = cache.get(key);
        long now = System.currentTimeMillis();

        if (entry == null || now - entry.windowStart >= WINDOW_MS) {
            entry = new RateLimitEntry(now, 0);
            cache.put(key, entry);
        }

        if (entry.count >= MAX_ATTEMPTS) {
            long waitMinutes = (WINDOW_MS - (now - entry.windowStart)) / 60_000;
            response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write(objectMapper.writeValueAsString(
                    ApiResponse.fail(429, "Too many registration attempts. Please try again in " + waitMinutes + " minutes.")
            ));
            return;
        }

        entry.count++;
        filterChain.doFilter(request, response);
    }

    private String getClientIp(HttpServletRequest request) {
        String xfHeader = request.getHeader("X-Forwarded-For");
        if (xfHeader == null || xfHeader.isEmpty()) {
            return request.getRemoteAddr();
        }
        return xfHeader.split(",")[0].trim();
    }

    private static class RateLimitEntry {
        final long windowStart;
        volatile int count;

        RateLimitEntry(long windowStart, int count) {
            this.windowStart = windowStart;
            this.count = count;
        }
    }
}
