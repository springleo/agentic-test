package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

@RestController
public class MathController {

    @GetMapping("/")
    public Map<String, String> root() {
        Map<String, String> info = new HashMap<>();
        info.put("usage", "GET /add?a=<int>&b=<int>");
        info.put("description", "Returns JSON {a,b,sum}");
        return info;
    }

    @GetMapping("/add")
    public ResponseEntity<Map<String, Object>> add(@RequestParam(required = false) Integer a,
                                                   @RequestParam(required = false) Integer b) {
        if (a == null || b == null) {
            Map<String, Object> err = new HashMap<>();
            err.put("error", "Missing parameter 'a' or 'b'");
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(err);
        }

        Map<String, Object> result = new HashMap<>();
        result.put("a", a);
        result.put("b", b);
        result.put("sum", a + b);
        return ResponseEntity.ok(result);
    }
}
