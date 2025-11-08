package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MathControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void addReturnsSum() throws Exception {
        mockMvc.perform(get("/add").param("a", "3").param("b", "4"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"a\":3,\"b\":4,\"sum\":7}"));
    }
    
    @Test
    void addMissingParamsReturnsBadRequest() throws Exception {
        mockMvc.perform(get("/add"))
                .andExpect(status().isBadRequest())
                .andExpect(content().json("{\"error\":\"Missing parameter 'a' or 'b'\"}"));
    }
}
