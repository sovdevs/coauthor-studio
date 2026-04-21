  ---                                                                                                                                                                                               
  uv run af — project management         
                                                                                                                                                                                                    
  uv run af init                           create a new project (wizard)                              
  uv run af list                           list all projects                                                                                                                                        
  uv run af write <project_id>             open a writing session (CLI)
  uv run af draft <project_id>             export finalized segments to stdout                                                                                                                      
  uv run af draft <project_id> -o out.txt  export to file                                             
  uv run af-web                            start web UI at http://localhost:8000                                                                                                                    
                                                                                                                                                                                                    
  ---                                                                                                                                                                                               
  In-session commands (inside af write)                                                                                                                                                             
                                                                                                                                                                                                    
  Session                                
                                                                                                                                                                                                    
  :help              show all commands                                                                
  :q  :quit  :exit   quit                                                                                                                                                                           
  :mode              show mode and language
  :modules           list active modules                                                                                                                                                            
                                                                                                                                                                                                    
  Writing                                                                                                                                                                                           
                                                                                                                                                                                                    
  :del <n>           delete displayed segment number n                                                
                                                                                                                                                                                                    
  Chapters
                                                                                                                                                                                                    
  :chapters          list all chapters                                                                
  :c <n or id>       switch chapter      
  :new [title]       create a new chapter                                                                                                                                                           
                                                                                                                                                                                                    
  Lexical                                                                                                                                                                                           
                                                                                                                                                                                                    
  :d <word>          dictionary lookup                                                                
  :t <word>          thesaurus lookup    
                                                                                                                                                                                                    
  Character Builder
                                                                                                                                                                                                    
  :cb list                               list all characters                                          
  :cb show <id>                          print full profile (Markdown)                                                                                                                              
  :cb create                             create a character (interview)                                                                                                                             
  :cb edit <id>                          edit a character (interview)                                                                                                                               
  :cb duplicate <id>                     copy a character                                                                                                                                           
  :cb delete <id>                        delete a character                                                                                                                                         
  :cb export <id>                        print Markdown dossier
                                                                                                                                                                                                    
  :cb dialog <idA> <idB> --setting "…"   generate dialog draft                                                                                                                                      
  :cb scene  <idA> <idB> --setting "…"   generate scene draft                                                                                                                                       
    (same ID twice = internal self-dialogue)                                                                                                                                                        
    --quote-mode auto|light|strong                                                                                                                                                                  
    --allow-direct-quotes                                                                                                                                                                           
    --include-authorial-material                                                                                                                                                                    
                                                                                                                                                                                                    
  :cb extract <author_dir>               extract draft characters from author package                                                                                                               
  :cb extract <author_dir> --include-narrator   also extract per-book narrator profiles                                                                                                             
                                                                                                                                                                                                    
  ---                                                                                                 
  uv run python -m augmented_fiction.modules.voice.turnofphrase — author packages                                                                                                                   
                                                                                                                                                                                                    
  Build an author pack (run once per author, processes all EPUBs in epubs/):
  uv run python -m augmented_fiction.modules.voice.turnofphrase run <author_folder>                                                                                                                 
  uv run python -m augmented_fiction.modules.voice.turnofphrase run <author_folder> --epub "filename.epub"
                                                                                                                                                                                                    
  Abstraction pass (offline LLM step, run after run):                                                                                                                                               
  uv run python -m augmented_fiction.modules.voice.turnofphrase abstract <author_folder>                                                                                                            
  uv run python -m augmented_fiction.modules.voice.turnofphrase abstract <author_folder> --model gpt-4o                                                                                             
                                                                                                                                                                                                    
  Generate a passage in the author's style:                                                                                                                                                         
  uv run python -m augmented_fiction.modules.voice.turnofphrase generate <author_folder> "prompt"                                                                                                   
    --words 180                                                                                                                                                                                     
    --mode dialogue|action|reflective|descriptive|narrative                                                                                                                                         
    --exemplars 3                                                                                     
    --model gpt-4o                                                                                                                                                                                  
    --save        (append to generated/generations.jsonl)                                             
    --rewrite     (second-pass dialogue rewrite)                                                                                                                                                    
    --debug       (print full generation packet)                                                      
                                                                                                                                                                                                    
  Search passages:
  uv run python -m augmented_fiction.modules.voice.turnofphrase search <author_folder> "query"                                                                                                      
    --kind quote|exemplar                                                                             
    --mode action|reflective|descriptive|narrative|dialogue                                                                                                                                         
    --context 0|1                                          
    --sentence-min N  --sentence-max N                                                                                                                                                              
    --dialogue-heavy                                                                                  
    --top 5                                                                                                                                                                                         
           
  Analyze text against an author profile:                                                                                                                                                           
  uv run python -m augmented_fiction.modules.voice.turnofphrase analyze <author_folder> "text"                                                                                                      
  uv run python -m augmented_fiction.modules.voice.turnofphrase analyze <author_folder> @path/to/file.txt
    --exemplars 5                                                                                                                                                                                   
                                                                                                                                                                                                    
  ---                                    
  Web UI — http://localhost:8000                                                                                                                                                                    
                                                                                                                                                                                                    
  /                    Projects list     
  /characters          Character Studio                                                                                                                                                             
  /characters/new      New character form                                                                                                                                                           
  /characters/<id>     Edit character    
  /dialog/new          Dialog generation + revision loop    