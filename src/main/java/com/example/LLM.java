package com.example;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.File;
import java.util.ArrayList;
import java.util.List;
class llmstore {
    public int id;
    public String name;
    @JsonProperty("filename_pattern")
    public String filenamePattern; 
    public String link;
    public String quantization;
    public String parameters;
    public String pros;
    public String cons;
}
public class LLM{
    public static List<String> llmsearch(int key){
        try{
            ObjectMapper mapper = new ObjectMapper();
            File jsonFile = new File("src/main/java/com/example/resources/jsonfiles/llmstore.json");
            llmstore[] models = mapper.readValue(jsonFile,llmstore[].class);
            for (llmstore content:models){
                if (content.id==key){
                    String link = content.link;
                    String filenamepattern = content.filenamePattern;
                    List<String> LLminformation = new ArrayList<>();
                    if (!(link==null || link.isEmpty())){
                        System.out.println(link);
                        LLminformation.add(link);
                        LLminformation.add(filenamepattern);
                        return LLminformation;
                    }
                }
            }
        }catch (Exception e){
            e.printStackTrace();
            return null;
        }
        return null;
    }
}
