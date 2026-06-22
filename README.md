# DocuSign Downloader em Python
Robô para isntalação de todos os "acordos" dentro do DocuSign, instalando CSV por página, todos os PDFs, verificação por ID Único para evitar arquivos corrompidos e dois logs (um para verificação e outro para erros), permitindo que diante de qualquer tipo de erro, o arquivo possa ser lidado manualmente com todos os detalhes.

## Especificações:
  Redução de esforço manual;  
  Mitigação de risco de perda documental no encerramento da conta do fornecedor;  
  Maior confiabilidade no backup;  
  Rastreabilidade por item;  
  Capacidade de auditoria posterior;  
  Identificação precisa de falhas e pendências;  


## Método de Utilização:
1. Instalação de requerimentos:

pip install -r requirements.txt

2. Rodar script:

python main.py


## Observações:
  Aproximadamente 8,8 arquivos / minuto
  Arquivos baixados do DocuSign podem apresentar um caso muito específico de "ID duplo" - um
  arquivo recebe assinatura digital, recebe o ID único, é baixado e assinado novamente, recebendo mais um ID no
  mesmo local. Quando o DocuSign é verificado, o ID "atrás" do novo é copiado, prevenindo a verificação via ID.
  Entretanto, o arquivo não está corrompido e via o log de validação é possível identificar o nome, ID e página, 
  permitindo a instalação manual do arquivo.

