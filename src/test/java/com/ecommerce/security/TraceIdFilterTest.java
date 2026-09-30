package com.ecommerce.security;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

class TraceIdFilterTest {
    @Test
    void propagatesSafeTraceIdAndClearsMdc() throws Exception {
        TraceIdFilter filter = new TraceIdFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER, "trace-agent-1234");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, (req, res) ->
                assertEquals("trace-agent-1234", MDC.get("traceId")));

        assertEquals("trace-agent-1234", response.getHeader(TraceIdFilter.HEADER));
        assertNull(MDC.get("traceId"));
    }

    @Test
    void replacesUnsafeTraceId() throws Exception {
        TraceIdFilter filter = new TraceIdFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(TraceIdFilter.HEADER, "bad value\nforged");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, (req, res) -> { });

        String generated = response.getHeader(TraceIdFilter.HEADER);
        assertFalse(generated.contains("bad value"));
        assertEquals(36, generated.length());
    }
}
