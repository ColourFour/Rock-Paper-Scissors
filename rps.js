function getComputerChoice(){
    let z = Math.random();
    if (z < 0.33){
        return "rock";
    }
    else if (z > 0.66){
        return "scissors";
    }
    else {
        return "paper";
    }
}

function getHumanChoice(){
    let q = prompt("Rock, paper, scissors");
    x = q.toLowerCase();
    return x;
}

let humanScore = 0;
let computerScore = 0;


function playRound(humanSelection,computerSelection){
if (humanSelection == computerSelection){
    return "We tie!";
}

if (humanSelection =="rock"){
    if (computerSelection =="scissors")
    {
        humanScore = humanScore + 1;
        return "You win! " + humanSelection +" beats " + computerSelection + "";
    }


    if (computerSelection =="paper")
    {
        computerScore = computerScore + 1;    
        return "You lose! " + computerSelection +" beats " + humanSelection + "";
    }
}

if (humanSelection =="paper"){
    if (computerSelection =="scissors")
    {
        computerScore = computerScore + 1; 
        return "You lose! " + computerSelection +" beats " + humanSelection + "";
    }


    if (computerSelection =="rock")
    {
        humanScore = humanScore + 1;
        return "You win! " + humanSelection +" beats " + computerSelection + "";
  
    }
    }

if (humanSelection =="scissors"){
    if (computerSelection =="rock")
    {
        computerScore = computerScore + 1; 
        return "You lose! " + computerSelection +" beats " + humanSelection + "";
       
    }


    if (computerSelection =="paper")
    {
        humanScore = humanScore + 1;   
        return "You win! " + humanSelection +" beats " + computerSelection + "";
    
    }
}
}

function playGame(){
    for(i=0; i<5; i = i+1){
        let humanSelection = getHumanChoice();
        let computerSelection = getComputerChoice();
        let result = playRound(humanSelection,computerSelection);
        console.log(result);
    }
}

playGame();
if(humanScore > computerScore){
    console.log("You won the match " + humanScore + " " + computerScore + "!");
}
else if(humanScore < computerScore){
    console.log("You lost the match! " + humanScore + " " + computerScore + "");
}
else{
    console.log( "It's a draw. " + humanScore + " " + computerScore + "");
}
