while extracting the table rows and coloumns , i had problems :
1 - it was giving error because of the everywhere it was not blank and I have given " | " so it was not retreiving 
2 - then after that it was extracted but not giving proper output only giving (Your retrieval is now finding wrong table rows because your query is too broad or your table database has too many irrelevant rows.)
3 - then we fixed it it was giving proper output to it 

Better data filtering > bigger retrieval **


creating a seperate file for calculation of metrics , rather than telling the local LLM to do it , becuase LLMs are not good at calculating they are good at finding patterns


the whole extraction failed becuase I didnt analyzed the types of tables and their border in pdf, before I was using pyplumber python and now I am using pymupdf

json had many duplicates values so the llm was not extracting the values correctly and calculating margin wrong , so we solved that

using fuzzy matching (a programming technique used to find strings that are similar but not identical, example - amazon, amazom.com) for metrics in various upcoming pdfs


after the GraphRAG was made we excountered the HUB problem, which comes after the hub node is connected to many other entities and the LLM isnt able to traverse them all and therefore it doesn't provide correct output, 

In this case we have to combine both the Vector RAG and Graph RAG for good quality output